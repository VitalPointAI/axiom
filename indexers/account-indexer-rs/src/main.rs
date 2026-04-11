//! Account Block Index Builder — Rust fetcher for neardata.xyz archives.
//!
//! Fetches .tgz archives in parallel, extracts account IDs, and streams
//! tab-separated (account_int, segment_start) integer pairs to stdout continuously.
//! Workers send results through a channel so the writer never blocks fetching.
//!
//! The writer thread owns a DictionaryCache that resolves account ID strings
//! to integer IDs via the PostgreSQL account_dictionary table. The cache is
//! pre-warmed at startup and grows lazily for new accounts. Segment start is
//! calculated as (block_height / 1000) * 1000.

use clap::Parser;
use flate2::read::GzDecoder;
use std::collections::{HashMap, HashSet};
use std::io::{self, BufWriter, Cursor, Read, Write};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::time::Instant;
use tar::Archive;

use postgres::{Client, NoTls};

const ARCHIVE_BOUNDARIES: &[u64] = &[122_000_000, 142_000_000];
const BLOCKS_PER_ARCHIVE: u64 = 10;

// ─── CLI Arguments ─────────────────────────────────────────────────────────

#[derive(Parser)]
#[command(name = "account-indexer-rs")]
struct Args {
    #[arg(long)]
    start: u64,
    #[arg(long)]
    end: u64,
    #[arg(long, env = "FASTNEAR_API_KEY", default_value = "")]
    api_key: String,
    #[arg(long, default_value = "16")]
    workers: usize,
    #[arg(long, default_value = "500")]
    progress_interval: u64,
    /// PostgreSQL connection string for the account_dictionary table.
    /// Example: postgresql://neartax:pass@127.0.0.1:5433/neartax
    #[arg(long, env = "DATABASE_URL")]
    database_url: String,
}

// ─── Dictionary Cache ───────────────────────────────────────────────────────

/// In-memory HashMap backed by the PostgreSQL account_dictionary table.
///
/// The cache is pre-warmed at startup by loading the full dictionary into
/// a HashMap<String, i32>. For new accounts, resolve() inserts them into
/// the dictionary via an upsert and caches the returned ID.
///
/// Thread safety: this struct is NOT thread-safe. It is owned exclusively
/// by the writer thread (single-threaded dictionary access avoids any locking).
struct DictionaryCache {
    /// Maps account_id string → integer id (from account_dictionary.id)
    cache: HashMap<String, i32>,
    /// Blocking PostgreSQL connection used for dictionary lookups/inserts
    client: Client,
    /// Saved connection string for reconnection on idle timeout
    database_url: String,
}

impl DictionaryCache {
    /// Connect to PostgreSQL and pre-allocate the HashMap.
    fn new(database_url: &str) -> Self {
        let client = Self::connect(database_url);
        Self {
            cache: HashMap::with_capacity(20_000_000), // pre-allocate for ~15M accounts
            client,
            database_url: database_url.to_string(),
        }
    }

    /// Parse the URL, enable TCP keepalives (guards against idle timeout during
    /// long archive fetch windows), and connect.
    fn connect(database_url: &str) -> Client {
        let mut config = database_url
            .parse::<postgres::Config>()
            .expect("Invalid DATABASE_URL");
        config.keepalives(true);
        config.keepalives_idle(std::time::Duration::from_secs(30));
        config
            .connect(NoTls)
            .expect("Failed to connect to PostgreSQL for account_dictionary")
    }

    /// Load the entire account_dictionary table into the in-memory HashMap.
    ///
    /// Called once at startup before the writer loop begins. After this,
    /// the vast majority of resolve() calls will be fast cache hits.
    fn warm_cache(&mut self) {
        let rows = self
            .client
            .query("SELECT id, account_id FROM account_dictionary", &[])
            .expect("Failed to pre-warm dictionary cache from PostgreSQL");
        let count = rows.len();
        for row in rows {
            let id: i32 = row.get(0);
            let account_id: String = row.get(1);
            self.cache.insert(account_id, id);
        }
        eprintln!("Dictionary pre-warm complete: {} entries", count);
    }

    /// Resolve an account ID string to its integer ID.
    ///
    /// 1. Fast path: return from in-memory cache (>99% of calls after warm).
    /// 2. DB lookup: SELECT id FROM account_dictionary WHERE account_id = $1
    /// 3. DB insert: INSERT ... ON CONFLICT ... RETURNING id (upsert for new accounts)
    ///
    /// If any PG query fails with a connection error, the connection is
    /// re-established once and the query is retried.
    fn resolve(&mut self, account_id: &str) -> i32 {
        // 1. Cache hit (fast path)
        if let Some(&id) = self.cache.get(account_id) {
            return id;
        }

        // 2. DB lookup
        match self.query_opt_with_retry(
            "SELECT id FROM account_dictionary WHERE account_id = $1",
            account_id,
        ) {
            Some(id) => {
                self.cache.insert(account_id.to_string(), id);
                return id;
            }
            None => {} // fall through to insert
        }

        // 3. DB insert (upsert — safe for concurrent access)
        let id = self.insert_with_retry(account_id);
        self.cache.insert(account_id.to_string(), id);
        id
    }

    /// SELECT id with a single reconnect-on-error retry.
    fn query_opt_with_retry(&mut self, sql: &str, account_id: &str) -> Option<i32> {
        for attempt in 0..2 {
            match self.client.query_opt(sql, &[&account_id]) {
                Ok(Some(row)) => return Some(row.get(0)),
                Ok(None) => return None,
                Err(e) if attempt == 0 && Self::is_connection_error(&e) => {
                    eprintln!("Reconnecting to PostgreSQL after idle timeout: {}", e);
                    self.client = Self::connect(&self.database_url);
                }
                Err(e) => panic!("Dictionary lookup failed: {}", e),
            }
        }
        None
    }

    /// INSERT ... ON CONFLICT ... RETURNING id with a single reconnect-on-error retry.
    fn insert_with_retry(&mut self, account_id: &str) -> i32 {
        let sql = "INSERT INTO account_dictionary (account_id) VALUES ($1) \
                   ON CONFLICT (account_id) DO UPDATE SET account_id = EXCLUDED.account_id \
                   RETURNING id";
        for attempt in 0..2 {
            match self.client.query_one(sql, &[&account_id]) {
                Ok(row) => return row.get(0),
                Err(e) if attempt == 0 && Self::is_connection_error(&e) => {
                    eprintln!("Reconnecting to PostgreSQL after idle timeout: {}", e);
                    self.client = Self::connect(&self.database_url);
                }
                Err(e) => panic!("Dictionary insert failed: {}", e),
            }
        }
        unreachable!()
    }

    /// Heuristic: does the postgres error look like a lost connection?
    fn is_connection_error(e: &postgres::Error) -> bool {
        let s = e.to_string().to_lowercase();
        s.contains("connection") || s.contains("reset") || s.contains("broken pipe")
            || s.contains("eof") || s.contains("io error")
    }
}

// ─── Archive fetching (workers — unchanged) ─────────────────────────────────

fn archive_url(block_height: u64) -> String {
    let padded = format!("{:012}", block_height);
    let node_idx = ARCHIVE_BOUNDARIES
        .iter()
        .position(|&b| block_height < b)
        .unwrap_or(ARCHIVE_BOUNDARIES.len());
    format!(
        "https://a{}.mainnet.neardata.xyz/raw/{}/{}/{}.tgz",
        node_idx, &padded[..6], &padded[6..9], padded
    )
}

fn align_down(block: u64) -> u64 {
    (block / BLOCKS_PER_ARCHIVE) * BLOCKS_PER_ARCHIVE
}

fn fetch_and_extract(
    archive_block: u64,
    client: &reqwest::blocking::Client,
    api_key: &str,
) -> Vec<(String, u64)> {
    let url = archive_url(archive_block);

    for attempt in 0..3 {
        let mut req = client.get(&url);
        if !api_key.is_empty() {
            req = req.header("Authorization", format!("Bearer {}", api_key));
        }
        let resp = match req.send() {
            Ok(r) => r,
            Err(_) => {
                if attempt < 2 { std::thread::sleep(std::time::Duration::from_secs(2)); }
                continue;
            }
        };

        if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
            std::thread::sleep(std::time::Duration::from_secs(5));
            continue;
        }
        if resp.status() == reqwest::StatusCode::NOT_FOUND || !resp.status().is_success() {
            return Vec::new();
        }

        let bytes = match resp.bytes() {
            Ok(b) => b,
            Err(_) => continue,
        };

        let decoder = GzDecoder::new(Cursor::new(&bytes));
        let mut archive = Archive::new(decoder);
        let entries = match archive.entries() {
            Ok(e) => e,
            Err(_) => return Vec::new(),
        };

        let mut pairs = Vec::new();

        for entry in entries {
            let mut entry = match entry {
                Ok(e) => e,
                Err(_) => continue,
            };
            let mut buf = Vec::new();
            if entry.read_to_end(&mut buf).is_err() { continue; }

            let block: serde_json::Value = match serde_json::from_slice(&buf) {
                Ok(v) => v,
                Err(_) => continue,
            };

            let height = block.pointer("/block/header/height")
                .and_then(|v| v.as_u64()).unwrap_or(0);
            if height == 0 { continue; }

            let mut accounts = HashSet::new();

            if let Some(shards) = block.get("shards").and_then(|s| s.as_array()) {
                for shard in shards {
                    if let Some(chunk) = shard.get("chunk") {
                        if let Some(txs) = chunk.get("transactions").and_then(|t| t.as_array()) {
                            for tx in txs {
                                if let Some(td) = tx.get("transaction") {
                                    if let Some(s) = td.get("signer_id").and_then(|v| v.as_str()) {
                                        if s != "system" { accounts.insert(s.to_lowercase()); }
                                    }
                                    if let Some(r) = td.get("receiver_id").and_then(|v| v.as_str()) {
                                        if r != "system" { accounts.insert(r.to_lowercase()); }
                                    }
                                }
                            }
                        }
                    }
                    // Receipt execution outcomes: only index receiver_id (where actions land).
                    // predecessor_id is typically a contract (not a user wallet) and
                    // inflates the index ~30% with data that doesn't help wallet lookups.
                    if let Some(reos) = shard.get("receipt_execution_outcomes").and_then(|r| r.as_array()) {
                        for reo in reos {
                            if let Some(receipt) = reo.get("receipt") {
                                if let Some(r) = receipt.get("receiver_id").and_then(|v| v.as_str()) {
                                    if r != "system" { accounts.insert(r.to_lowercase()); }
                                }
                            }
                        }
                    }
                }
            }

            for acct in accounts {
                pairs.push((acct, height));
            }
        }
        return pairs;
    }
    Vec::new()
}

// ─── Main ───────────────────────────────────────────────────────────────────

fn main() {
    let args = Args::parse();

    let start = align_down(args.start);
    let end = align_down(args.end);
    let total_archives = (end - start) / BLOCKS_PER_ARCHIVE + 1;
    let api_key = args.api_key.clone();
    let workers = args.workers;
    let progress_interval = args.progress_interval;
    let database_url = args.database_url.clone();

    eprintln!(
        "account-indexer-rs: blocks {} → {} ({} archives, {} workers)",
        start, end, total_archives, workers
    );

    let archives_done = AtomicU64::new(0);
    let timer = Instant::now();

    // Channel: workers send (account_string, block_height) pairs.
    // The writer thread resolves strings to integer IDs via DictionaryCache.
    let (tx, rx) = mpsc::sync_channel::<Vec<(String, u64)>>(workers * 4);

    // Spawn writer thread — owns DictionaryCache, resolves strings to ints,
    // emits "account_int\tsegment_start\n" to stdout.
    let writer_handle = std::thread::spawn(move || {
        // Create and warm the dictionary cache
        let mut dict_cache = DictionaryCache::new(&database_url);
        dict_cache.warm_cache();

        let stdout = io::stdout();
        let mut writer = BufWriter::with_capacity(1 << 20, stdout.lock());
        let mut total_pairs: u64 = 0;

        for pairs in rx {
            for (account_string, block_height) in &pairs {
                // Resolve account string → integer ID (cache hit >99% after warm)
                let account_int = dict_cache.resolve(account_string);
                // Segment start: round block_height down to nearest 1000
                let segment_start = (block_height / 1000) * 1000;
                let _ = write!(writer, "{}\t{}\n", account_int, segment_start as i32);
            }
            total_pairs += pairs.len() as u64;
            // Flush periodically to keep COPY fed
            if total_pairs % 100_000 < 1000 {
                let _ = writer.flush();
            }
        }
        let _ = writer.flush();
        total_pairs
    });

    // Spawn worker threads (unchanged — still extract (String, u64) pairs)
    let mut handles = Vec::new();
    let archive_heights: Vec<u64> = (0..total_archives)
        .map(|i| start + i * BLOCKS_PER_ARCHIVE)
        .collect();

    // Split work evenly across workers
    let chunks: Vec<Vec<u64>> = archive_heights
        .chunks((archive_heights.len() / workers).max(1))
        .map(|c| c.to_vec())
        .collect();

    for chunk in chunks {
        let tx = tx.clone();
        let api_key = api_key.clone();
        let archives_done = &archives_done as *const AtomicU64 as usize;
        let total_archives = total_archives;
        let progress_interval = progress_interval;

        let handle = std::thread::spawn(move || {
            let archives_done = unsafe { &*(archives_done as *const AtomicU64) };
            let client = reqwest::blocking::Client::builder()
                .pool_max_idle_per_host(4)
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("Failed to build HTTP client");

            for archive_block in chunk {
                let pairs = fetch_and_extract(archive_block, &client, &api_key);
                if !pairs.is_empty() {
                    let _ = tx.send(pairs);
                }

                let done = archives_done.fetch_add(1, Ordering::Relaxed) + 1;
                if done % progress_interval == 0 {
                    eprintln!(
                        "Progress: {}/{} archives ({:.1}%)",
                        done, total_archives,
                        done as f64 / total_archives as f64 * 100.0,
                    );
                }
            }
        });
        handles.push(handle);
    }

    // Drop our sender so the channel closes when all workers finish
    drop(tx);

    // Wait for all workers
    for h in handles {
        let _ = h.join();
    }

    // Wait for writer
    let total_pairs = writer_handle.join().unwrap_or(0);

    let elapsed = timer.elapsed().as_secs_f64();
    let total_blocks = total_archives * BLOCKS_PER_ARCHIVE;
    eprintln!(
        "Done: {} pairs from {} blocks in {:.1}s ({:.0} blocks/sec)",
        total_pairs, total_blocks, elapsed,
        total_blocks as f64 / elapsed
    );
}
