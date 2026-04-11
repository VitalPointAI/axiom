//! Account Block Index Builder — Rust fetcher for neardata.xyz archives.
//!
//! Fetches .tgz archives in parallel, extracts account IDs, and streams
//! tab-separated (account_id, block_height) pairs to stdout continuously.
//! Workers send results through a channel so the writer never blocks fetching.

use clap::Parser;
use flate2::read::GzDecoder;
use std::collections::HashSet;
use std::io::{self, BufWriter, Cursor, Read, Write};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::time::Instant;
use tar::Archive;

const ARCHIVE_BOUNDARIES: &[u64] = &[122_000_000, 142_000_000];
const BLOCKS_PER_ARCHIVE: u64 = 10;

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
}

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

fn main() {
    let args = Args::parse();

    let start = align_down(args.start);
    let end = align_down(args.end);
    let total_archives = (end - start) / BLOCKS_PER_ARCHIVE + 1;
    let api_key = args.api_key.clone();
    let workers = args.workers;
    let progress_interval = args.progress_interval;

    eprintln!(
        "account-indexer-rs: blocks {} → {} ({} archives, {} workers)",
        start, end, total_archives, workers
    );

    let archives_done = AtomicU64::new(0);
    let timer = Instant::now();

    // Channel: workers send pairs, main thread writes to stdout
    let (tx, rx) = mpsc::sync_channel::<Vec<(String, u64)>>(workers * 4);

    // Spawn writer thread — drains channel to stdout
    let writer_handle = std::thread::spawn(move || {
        let stdout = io::stdout();
        let mut writer = BufWriter::with_capacity(1 << 20, stdout.lock());
        let mut total_pairs: u64 = 0;

        for pairs in rx {
            for (account, height) in &pairs {
                let _ = write!(writer, "{}\t{}\n", account, height);
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

    // Spawn worker threads
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
        let timer_start = timer.elapsed().as_secs_f64(); // capture offset

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
                    // Can't easily share timer across threads, use done count for rate
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
