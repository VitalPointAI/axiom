//! Account Transactions Index Builder — streams blocks from neardata.xyz
//! via the official fastnear-neardata-fetcher crate and emits block-precise
//! per-account pointers to stdout for COPY loading into PostgreSQL.
//!
//! Output format (tab-separated, 2 columns per row):
//!     account_int \t block_height
//!
//! - account_int: integer ID from `account_dictionary` (resolved via cache)
//! - block_height: INTEGER block height where the account has activity
//!
//! Rows are deduplicated within each block so the output is at most one
//! (account_int, block_height) pair per account per block. This keeps
//! storage to ~8 bytes per row (~55 GB total for the whole chain).
//!
//! The writer accumulates a batch of blocks, bulk-upserts any new accounts
//! into the dictionary in a single round-trip, then writes the COPY lines.
//! This avoids the per-account insert latency that otherwise dominates
//! cold-start runs.
//!
//! Account sources captured:
//! - Chunk transactions: rows for both signer_id and receiver_id
//! - Receipt execution outcomes: rows for BOTH predecessor_id AND receiver_id
//!   (when originating tx_hash is known, i.e. user-initiated receipts)
//!
//! Predecessor_id IS indexed because the Python wallet sync code
//! (neardata_client.py::extract_wallet_txs) matches on either predecessor
//! or receiver for receipts. Omitting predecessor here would silently miss
//! cross-contract callback receipts that land on user wallets and cause
//! tax reports to undercount transactions.

use clap::Parser;
use std::collections::{HashMap, HashSet};
use std::io::{self, BufWriter, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use fastnear_neardata_fetcher::fetcher::{start_fetcher, FetcherConfigBuilder};
use fastnear_primitives::block_with_tx_hash::BlockWithTxHashes;
use fastnear_primitives::near_indexer_primitives::types::Finality;
use fastnear_primitives::types::ChainId;
use postgres::{Client, NoTls};
use tokio::sync::mpsc;

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
    /// Number of parallel fetcher threads (controls concurrent archive downloads)
    #[arg(long, default_value = "16")]
    workers: usize,
    /// How often to log progress (in blocks)
    #[arg(long, default_value = "5000")]
    progress_interval: u64,
    /// PostgreSQL connection string for the account_dictionary table.
    /// Example: postgresql://neartax:pass@127.0.0.1:5433/neartax
    #[arg(long, env = "DATABASE_URL")]
    database_url: String,
}

// ─── Dictionary Cache ───────────────────────────────────────────────────────

/// In-memory HashMap backed by the PostgreSQL `account_dictionary` table.
/// Owned exclusively by the writer thread (single-threaded DB access).
struct DictionaryCache {
    cache: HashMap<String, i32>,
    client: Client,
    database_url: String,
}

impl DictionaryCache {
    fn new(database_url: &str) -> Self {
        let client = Self::connect(database_url);
        Self {
            cache: HashMap::with_capacity(20_000_000),
            client,
            database_url: database_url.to_string(),
        }
    }

    fn connect(database_url: &str) -> Client {
        let mut config = database_url
            .parse::<postgres::Config>()
            .expect("Invalid DATABASE_URL");
        config.keepalives(true);
        config.keepalives_idle(Duration::from_secs(30));
        config
            .connect(NoTls)
            .expect("Failed to connect to PostgreSQL for account_dictionary")
    }

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

    /// Bulk-insert any accounts from `candidates` that aren't in the cache.
    /// A single round-trip handles many new accounts at once, which avoids
    /// the per-account INSERT latency that dominates cold-start runs.
    fn bulk_resolve(&mut self, candidates: &HashSet<String>) {
        let missing: Vec<&str> = candidates
            .iter()
            .filter(|a| !self.cache.contains_key(a.as_str()))
            .map(|a| a.as_str())
            .collect();
        if missing.is_empty() {
            return;
        }

        let sql = "INSERT INTO account_dictionary (account_id) \
                   SELECT * FROM UNNEST($1::text[]) \
                   ON CONFLICT (account_id) DO UPDATE SET account_id = EXCLUDED.account_id \
                   RETURNING id, account_id";
        let missing_vec: Vec<String> = missing.iter().map(|s| s.to_string()).collect();
        for attempt in 0..2 {
            match self.client.query(sql, &[&missing_vec]) {
                Ok(rows) => {
                    for row in rows {
                        let id: i32 = row.get(0);
                        let account_id: String = row.get(1);
                        self.cache.insert(account_id, id);
                    }
                    return;
                }
                Err(e) if attempt == 0 && Self::is_connection_error(&e) => {
                    eprintln!("Reconnecting to PostgreSQL after idle timeout: {}", e);
                    self.client = Self::connect(&self.database_url);
                }
                Err(e) => panic!("Bulk dictionary upsert failed: {}", e),
            }
        }
    }

    fn is_connection_error(e: &postgres::Error) -> bool {
        let s = e.to_string().to_lowercase();
        s.contains("connection")
            || s.contains("reset")
            || s.contains("broken pipe")
            || s.contains("eof")
            || s.contains("io error")
    }
}

// ─── Account extraction ────────────────────────────────────────────────────

/// Extract the set of accounts that have any user-visible activity in a block.
///
/// Sources:
///   - Chunk transactions: signer_id and receiver_id
///   - Receipt execution outcomes: BOTH predecessor_id and receiver_id
///     (when originating tx_hash is known)
///
/// Returns a set so each block contributes at most one (account, block) row
/// per account. Must stay in lockstep with `neardata_client.py::extract_wallet_txs`
/// — if that function looks at a field to match the wallet, we must index it
/// here or the wallet sync will silently miss data.
fn extract_block_accounts(block: &BlockWithTxHashes) -> (u64, HashSet<String>) {
    let height = block.block.header.height;
    let mut accounts: HashSet<String> = HashSet::new();

    for shard in &block.shards {
        if let Some(chunk) = &shard.chunk {
            for tx in &chunk.transactions {
                let signer = tx.transaction.signer_id.as_str();
                let receiver = tx.transaction.receiver_id.as_str();
                if signer != "system" {
                    accounts.insert(signer.to_lowercase());
                }
                if receiver != "system" {
                    accounts.insert(receiver.to_lowercase());
                }
            }
        }
        for reo in &shard.receipt_execution_outcomes {
            // Only index receipts whose originating tx_hash is known.
            // Unknown tx_hash happens for system-initiated receipts
            // (validator rewards, etc.) which aren't user-visible transactions.
            if reo.tx_hash.is_some() {
                let predecessor = reo.receipt.predecessor_id.as_str();
                let receiver = reo.receipt.receiver_id.as_str();
                if predecessor != "system" {
                    accounts.insert(predecessor.to_lowercase());
                }
                if receiver != "system" {
                    accounts.insert(receiver.to_lowercase());
                }
            }
        }
    }

    (height, accounts)
}

// ─── Writer thread ─────────────────────────────────────────────────────────

/// Batch size (in blocks) for dictionary bulk-upserts.
/// Larger = fewer round-trips, but higher memory / latency per flush.
const WRITER_BATCH_BLOCKS: usize = 200;

fn writer_thread(
    database_url: String,
    mut rx: mpsc::Receiver<(u64, HashSet<String>)>,
    progress_interval: u64,
    is_running: Arc<AtomicBool>,
) -> u64 {
    let mut dict_cache = DictionaryCache::new(&database_url);
    dict_cache.warm_cache();

    let stdout = io::stdout();
    let mut writer = BufWriter::with_capacity(1 << 20, stdout.lock());
    let mut total_rows: u64 = 0;
    let mut total_blocks: u64 = 0;
    let mut last_progress_block: u64 = 0;
    let start = Instant::now();

    // Accumulate a batch of (height, accounts) before flushing so we can
    // bulk-upsert all new dictionary entries in a single round-trip.
    let mut batch: Vec<(u64, HashSet<String>)> = Vec::with_capacity(WRITER_BATCH_BLOCKS);

    let flush_batch = |batch: &mut Vec<(u64, HashSet<String>)>,
                       dict: &mut DictionaryCache,
                       writer: &mut BufWriter<io::StdoutLock>,
                       total_rows: &mut u64| {
        if batch.is_empty() {
            return;
        }
        // Union all unique account strings across the batch, bulk-upsert new ones
        let mut all_accounts: HashSet<String> = HashSet::new();
        for (_, accounts) in batch.iter() {
            for a in accounts {
                all_accounts.insert(a.clone());
            }
        }
        dict.bulk_resolve(&all_accounts);

        // Emit one (account_int, block_height) row per unique account per block.
        // The HashSet already deduplicates within a block.
        for (height, accounts) in batch.drain(..) {
            let block_height_i32 = height as i32;
            for account in &accounts {
                if let Some(&account_int) = dict.cache.get(account) {
                    let _ = writeln!(writer, "{}\t{}", account_int, block_height_i32);
                    *total_rows += 1;
                }
            }
        }
    };

    while let Some((height, accounts)) = rx.blocking_recv() {
        if !is_running.load(Ordering::SeqCst) {
            break;
        }
        batch.push((height, accounts));
        total_blocks += 1;

        if batch.len() >= WRITER_BATCH_BLOCKS {
            flush_batch(&mut batch, &mut dict_cache, &mut writer, &mut total_rows);
        }

        if height >= last_progress_block + progress_interval {
            let _ = writer.flush();
            let elapsed = start.elapsed().as_secs_f64();
            let rate = total_blocks as f64 / elapsed;
            eprintln!(
                "Progress: block {} | {} blocks | {} rows | {:.0} blocks/sec",
                height, total_blocks, total_rows, rate
            );
            last_progress_block = height;
        }
    }

    flush_batch(&mut batch, &mut dict_cache, &mut writer, &mut total_rows);
    let _ = writer.flush();
    total_rows
}

// ─── Main ───────────────────────────────────────────────────────────────────

#[tokio::main(flavor = "multi_thread")]
async fn main() {
    let args = Args::parse();

    eprintln!(
        "account-indexer-rs v0.3 (tx pointers + fastnear-neardata-fetcher): blocks {} → {} ({} threads)",
        args.start, args.end, args.workers
    );

    let is_running = Arc::new(AtomicBool::new(true));
    let is_running_ctrl = is_running.clone();
    ctrlc::set_handler(move || {
        is_running_ctrl.store(false, Ordering::SeqCst);
        eprintln!("Received Ctrl+C, shutting down...");
    })
    .ok();

    // Channel: fetcher → bridge stage → writer
    let (block_tx, mut block_rx) = mpsc::channel::<BlockWithTxHashes>(args.workers * 4);
    let (acct_tx, acct_rx) = mpsc::channel::<(u64, HashSet<String>)>(args.workers * 4);

    // Build fetcher config
    let mut config_builder = FetcherConfigBuilder::new()
        .num_threads(args.workers as u64)
        .num_lookahead_threads(4)
        .chain_id(ChainId::Mainnet)
        .finality(Finality::Final)
        .start_block_height(args.start)
        .end_block_height(args.end)
        .user_agent("axiom-account-indexer/0.3".to_string())
        .timeout_duration(Duration::from_secs(30))
        .retry_duration(Duration::from_secs(2));
    if !args.api_key.is_empty() {
        config_builder = config_builder.auth_bearer_token(args.api_key.clone());
    }
    let fetcher_config = config_builder.build();

    // Spawn the fetcher (async)
    let fetcher_running = is_running.clone();
    let fetcher_handle = tokio::spawn(async move {
        start_fetcher(fetcher_config, block_tx, fetcher_running).await;
    });

    // Spawn the writer (blocking, dedicated thread)
    let database_url = args.database_url.clone();
    let writer_running = is_running.clone();
    let progress_interval = args.progress_interval;
    let writer_handle = tokio::task::spawn_blocking(move || {
        writer_thread(database_url, acct_rx, progress_interval, writer_running)
    });

    // Bridge: receive typed blocks, extract accounts, forward to writer.
    let bridge_handle = tokio::spawn(async move {
        while let Some(block) = block_rx.recv().await {
            let (height, accounts) = extract_block_accounts(&block);
            if accounts.is_empty() {
                continue;
            }
            if acct_tx.send((height, accounts)).await.is_err() {
                break;
            }
        }
        drop(acct_tx);
    });

    let timer = Instant::now();

    if let Err(e) = fetcher_handle.await {
        eprintln!("Fetcher task error: {}", e);
    }
    if let Err(e) = bridge_handle.await {
        eprintln!("Bridge task error: {}", e);
    }

    let total_rows = writer_handle.await.unwrap_or(0);

    let elapsed = timer.elapsed().as_secs_f64();
    let total_blocks = args.end.saturating_sub(args.start);
    eprintln!(
        "Done: {} pointer rows from {} blocks in {:.1}s ({:.0} blocks/sec)",
        total_rows,
        total_blocks,
        elapsed,
        total_blocks as f64 / elapsed.max(0.001)
    );
}
