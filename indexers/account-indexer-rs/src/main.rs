//! Account Block Index Builder — Rust fetcher for neardata.xyz archives.
//!
//! Fetches .tgz archives from neardata.xyz archive nodes, extracts all
//! account IDs (signer, receiver, predecessor) from each block, and
//! outputs tab-separated (account_id, block_height) pairs to stdout.
//!
//! The Python account_indexer.py wrapper pipes this output into PostgreSQL
//! via COPY FROM STDIN for maximum insert throughput.
//!
//! Usage:
//!     account-indexer-rs --start 42000000 --end 50000000 --api-key KEY
//!     account-indexer-rs --start 42000000 --end 50000000 --api-key KEY --workers 16

use clap::Parser;
use flate2::read::GzDecoder;
use rayon::prelude::*;
use std::collections::HashSet;
use std::io::{self, BufWriter, Cursor, Read, Write};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;
use tar::Archive;

/// Archive node routing boundaries (from fastnear-neardata-fetcher)
const ARCHIVE_BOUNDARIES: &[u64] = &[122_000_000, 142_000_000];
const BLOCKS_PER_ARCHIVE: u64 = 10;

#[derive(Parser)]
#[command(name = "account-indexer-rs")]
#[command(about = "Fast NEAR account block index builder using neardata.xyz archives")]
struct Args {
    /// Start block height (will be aligned down to nearest archive boundary)
    #[arg(long)]
    start: u64,

    /// End block height
    #[arg(long)]
    end: u64,

    /// FastNear API key for authenticated access (removes rate limit)
    #[arg(long, env = "FASTNEAR_API_KEY", default_value = "")]
    api_key: String,

    /// Number of parallel workers
    #[arg(long, default_value = "16")]
    workers: usize,

    /// Print progress to stderr every N archives
    #[arg(long, default_value = "500")]
    progress_interval: u64,
}

fn archive_url(block_height: u64, api_key: &str) -> String {
    let padded = format!("{:012}", block_height);
    let p1 = &padded[..6];
    let p2 = &padded[6..9];

    let node_idx = ARCHIVE_BOUNDARIES
        .iter()
        .position(|&b| block_height < b)
        .unwrap_or(ARCHIVE_BOUNDARIES.len());

    let mut url = format!(
        "https://a{}.mainnet.neardata.xyz/raw/{}/{}/{}.tgz",
        node_idx, p1, p2, padded
    );
    if !api_key.is_empty() {
        url.push_str(&format!("?apiKey={}", api_key));
    }
    url
}

fn align_down(block: u64) -> u64 {
    (block / BLOCKS_PER_ARCHIVE) * BLOCKS_PER_ARCHIVE
}

/// Fetch one archive, parse all blocks, extract account pairs.
/// Returns Vec<(account_id, block_height)>.
fn fetch_and_extract(archive_block: u64, client: &reqwest::blocking::Client, api_key: &str) -> Vec<(String, u64)> {
    let url = archive_url(archive_block, api_key);

    for attempt in 0..3 {
        let resp = match client.get(&url).timeout(std::time::Duration::from_secs(30)).send() {
            Ok(r) => r,
            Err(_) => {
                if attempt < 2 {
                    std::thread::sleep(std::time::Duration::from_secs(2));
                }
                continue;
            }
        };

        if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
            std::thread::sleep(std::time::Duration::from_secs(5));
            continue;
        }

        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Vec::new();
        }

        if !resp.status().is_success() {
            continue;
        }

        let bytes = match resp.bytes() {
            Ok(b) => b,
            Err(_) => continue,
        };

        // Decompress .tgz
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
            if entry.read_to_end(&mut buf).is_err() {
                continue;
            }

            let block: serde_json::Value = match serde_json::from_slice(&buf) {
                Ok(v) => v,
                Err(_) => continue,
            };

            let height = block
                .pointer("/block/header/height")
                .and_then(|v| v.as_u64())
                .unwrap_or(0);

            if height == 0 {
                continue;
            }

            let mut accounts = HashSet::new();

            if let Some(shards) = block.get("shards").and_then(|s| s.as_array()) {
                for shard in shards {
                    // Transaction signers/receivers
                    if let Some(chunk) = shard.get("chunk") {
                        if let Some(txs) = chunk.get("transactions").and_then(|t| t.as_array()) {
                            for tx in txs {
                                if let Some(td) = tx.get("transaction") {
                                    if let Some(s) = td.get("signer_id").and_then(|v| v.as_str()) {
                                        if s != "system" {
                                            accounts.insert(s.to_lowercase());
                                        }
                                    }
                                    if let Some(r) = td.get("receiver_id").and_then(|v| v.as_str()) {
                                        if r != "system" {
                                            accounts.insert(r.to_lowercase());
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Receipt predecessors/receivers
                    if let Some(reos) = shard.get("receipt_execution_outcomes").and_then(|r| r.as_array()) {
                        for reo in reos {
                            if let Some(receipt) = reo.get("receipt") {
                                if let Some(p) = receipt.get("predecessor_id").and_then(|v| v.as_str()) {
                                    if p != "system" {
                                        accounts.insert(p.to_lowercase());
                                    }
                                }
                                if let Some(r) = receipt.get("receiver_id").and_then(|v| v.as_str()) {
                                    if r != "system" {
                                        accounts.insert(r.to_lowercase());
                                    }
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

fn main() {
    let args = Args::parse();

    rayon::ThreadPoolBuilder::new()
        .num_threads(args.workers)
        .build_global()
        .expect("Failed to build thread pool");

    let start = align_down(args.start);
    let end = align_down(args.end);
    let total_archives = (end - start) / BLOCKS_PER_ARCHIVE + 1;

    eprintln!(
        "account-indexer-rs: blocks {} → {} ({} archives, {} workers)",
        start, end, total_archives, args.workers
    );

    let archives_done = AtomicU64::new(0);
    let pairs_total = AtomicU64::new(0);
    let timer = Instant::now();

    let stdout = io::stdout();
    let mut writer = BufWriter::with_capacity(1 << 20, stdout.lock()); // 1MB buffer

    // Collect archive heights
    let archive_heights: Vec<u64> = (0..total_archives)
        .map(|i| start + i * BLOCKS_PER_ARCHIVE)
        .collect();

    // Process in chunks to control memory — each chunk is processed in parallel,
    // results written to stdout before starting the next chunk
    let chunk_size = args.workers * 64; // 64 archives per worker per chunk

    for chunk in archive_heights.chunks(chunk_size) {
        let results: Vec<Vec<(String, u64)>> = chunk
            .par_iter()
            .map(|&archive_block| {
                // Each rayon worker gets its own HTTP client (connection pooling per thread)
                thread_local! {
                    static CLIENT: reqwest::blocking::Client = reqwest::blocking::Client::builder()
                        .pool_max_idle_per_host(4)
                        .timeout(std::time::Duration::from_secs(30))
                        .build()
                        .expect("Failed to build HTTP client");
                }

                let pairs = CLIENT.with(|client| {
                    fetch_and_extract(archive_block, client, &args.api_key)
                });

                let done = archives_done.fetch_add(1, Ordering::Relaxed) + 1;
                pairs_total.fetch_add(pairs.len() as u64, Ordering::Relaxed);

                if done % args.progress_interval == 0 {
                    let elapsed = timer.elapsed().as_secs_f64();
                    let rate = (done as f64 * BLOCKS_PER_ARCHIVE as f64) / elapsed;
                    let remaining = total_archives - done;
                    let eta_hours = (remaining as f64 * BLOCKS_PER_ARCHIVE as f64) / rate / 3600.0;
                    eprintln!(
                        "Progress: {}/{} archives ({:.1}%) — {:.0} blocks/sec — {:.1}h remaining",
                        done, total_archives,
                        done as f64 / total_archives as f64 * 100.0,
                        rate, eta_hours
                    );
                }

                pairs
            })
            .collect();

        // Write all pairs from this chunk to stdout
        for pairs in results {
            for (account, height) in pairs {
                let _ = write!(writer, "{}\t{}\n", account, height);
            }
        }
        let _ = writer.flush();
    }

    let elapsed = timer.elapsed().as_secs_f64();
    let total_pairs = pairs_total.load(Ordering::Relaxed);
    let total_blocks = total_archives * BLOCKS_PER_ARCHIVE;
    eprintln!(
        "Done: {} pairs from {} blocks in {:.1}s ({:.0} blocks/sec)",
        total_pairs, total_blocks, elapsed,
        total_blocks as f64 / elapsed
    );
}
