#!/usr/bin/env python3
"""
NearTax Hybrid Indexer - Scalable Multi-User Architecture

Design:
1. NEW WALLET → API backfill (minutes, not days)
2. REAL-TIME → Single stream monitors ALL wallets
3. SHARED → One indexer serves unlimited users

Components:
- WalletHistoryFetcher: On-demand backfill via API
- RealtimeMonitor: Watches new blocks for all wallets
- WalletRegistry: Central wallet tracking

Usage:
    # Backfill a single wallet
    python hybrid_indexer.py --backfill aaron.near
    
    # Start real-time monitor for all wallets
    python hybrid_indexer.py --realtime
    
    # Add wallet and backfill
    python hybrid_indexer.py --add-wallet aaron.near --user-id 1
"""

import asyncio
import aiohttp
import argparse
import json
import os
import sqlite3
import time
import signal
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set, Dict, List

# Paths
BASE = Path(__file__).parent.parent
DB_PATH = BASE / "neartax.db"
LOG_PATH = BASE / "logs" / "hybrid_indexer.log"
STATE_PATH = BASE / "realtime_state.json"

# APIs
NEARDATA = os.environ.get("NEARDATA_API_URL", "https://mainnet.neardata.xyz")
FASTNEAR_API = os.environ.get("FASTNEAR_API_URL", "https://api.fastnear.com")

# Config
REALTIME_POLL_INTERVAL = 1.2  # NEAR block time
BACKFILL_BATCH_SIZE = 100
MAX_RETRIES = 3

# Logging
LOG_PATH.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)
log = logging.getLogger(__name__)


class WalletRegistry:
    """Central registry of all tracked wallets across all users."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._cache: Set[str] = set()
        self._cache_time = 0
        self._cache_ttl = 60  # Refresh every 60 seconds
    
    def get_all_wallets(self) -> Set[str]:
        """Get all unique wallet addresses (lowercase for matching)."""
        now = time.time()
        if now - self._cache_time > self._cache_ttl:
            self._refresh_cache()
        return self._cache
    
    def _refresh_cache(self):
        """Refresh the wallet cache from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT DISTINCT LOWER(account_id) FROM wallets")
        self._cache = {row[0] for row in cursor.fetchall()}
        conn.close()
        self._cache_time = time.time()
        log.debug(f"Wallet cache refreshed: {len(self._cache)} wallets")
    
    def add_wallet(self, account_id: str, user_id: int, chain: str = 'NEAR') -> int:
        """Add a wallet to the registry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if wallet already exists for this user
        cursor.execute(
            "SELECT id FROM wallets WHERE user_id = ? AND LOWER(account_id) = LOWER(?)",
            (user_id, account_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return existing[0]
        
        # Insert new wallet
        cursor.execute("""
            INSERT INTO wallets (user_id, account_id, chain, sync_status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        """, (user_id, account_id, chain, datetime.now(timezone.utc).isoformat()))
        
        wallet_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Invalidate cache
        self._cache_time = 0
        log.info(f"Added wallet {account_id} for user {user_id}")
        
        return wallet_id
    
    def update_sync_status(self, wallet_id: int, status: str, tx_count: int = None):
        """Update wallet sync status."""
        conn = sqlite3.connect(self.db_path)
        if tx_count is not None:
            conn.execute(
                "UPDATE wallets SET sync_status = ?, last_sync = ?, tx_count = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), tx_count, wallet_id)
            )
        else:
            conn.execute(
                "UPDATE wallets SET sync_status = ?, last_sync = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), wallet_id)
            )
        conn.commit()
        conn.close()


class TransactionStore:
    """Handles transaction storage with deduplication."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
    
    def save_transaction(self, wallet_id: int, tx: Dict) -> bool:
        """Save a transaction, return True if new (not duplicate)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO transactions 
                (wallet_id, tx_hash, block_height, timestamp, tx_type, 
                 from_account, to_account, amount, token, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet_id,
                tx.get('hash'),
                tx.get('block_height'),
                tx.get('timestamp'),
                tx.get('tx_type', 'transfer'),
                tx.get('from_account'),
                tx.get('to_account'),
                tx.get('amount'),
                tx.get('token', 'NEAR'),
                json.dumps(tx.get('raw', {}))
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicate
        finally:
            conn.close()
    
    def save_transactions_batch(self, wallet_id: int, txs: List[Dict]) -> int:
        """Save multiple transactions, return count of new records."""
        if not txs:
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        saved = 0
        
        for tx in txs:
            try:
                cursor.execute("""
                    INSERT INTO transactions 
                    (wallet_id, tx_hash, block_height, timestamp, tx_type, 
                     from_account, to_account, amount, token, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id,
                    tx.get('hash'),
                    tx.get('block_height'),
                    tx.get('timestamp'),
                    tx.get('tx_type', 'transfer'),
                    tx.get('from_account'),
                    tx.get('to_account'),
                    tx.get('amount'),
                    tx.get('token', 'NEAR'),
                    json.dumps(tx.get('raw', {}))
                ))
                saved += 1
            except sqlite3.IntegrityError:
                pass  # Duplicate
        
        conn.commit()
        conn.close()
        return saved
    
    def get_wallet_id(self, account_id: str) -> Optional[int]:
        """Get wallet ID by account ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT id FROM wallets WHERE LOWER(account_id) = LOWER(?)",
            (account_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


class WalletHistoryFetcher:
    """
    Fetches historical transactions for a wallet using available APIs.
    
    Strategy:
    1. Try FastNEAR Explorer API (if available)
    2. Fall back to NearBlocks API (rate limited)
    3. As last resort, use NEARDATA block scanning
    """
    
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
    
    async def fetch_history(self, account_id: str, wallet_id: int, store: TransactionStore) -> int:
        """
        Fetch complete transaction history for a wallet.
        Returns total transactions saved.
        """
        log.info(f"Fetching history for {account_id}")
        
        # Try FastNEAR API first (for account info)
        account_info = await self._get_fastnear_account_info(account_id)
        if account_info:
            log.info(f"  Account has {len(account_info.get('tokens', []))} tokens, "
                    f"{len(account_info.get('pools', []))} staking positions")
        
        # For now, use NearBlocks API with rate limiting
        # (FastNEAR Explorer API not publicly available yet)
        total_saved = await self._fetch_from_nearblocks(account_id, wallet_id, store)
        
        return total_saved
    
    async def _get_fastnear_account_info(self, account_id: str) -> Optional[Dict]:
        """Get account info from FastNEAR API."""
        try:
            async with self.session.get(f"{FASTNEAR_API}/v1/account/{account_id}/full") as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            log.debug(f"FastNEAR API error: {e}")
        return None
    
    async def _fetch_from_nearblocks(self, account_id: str, wallet_id: int, 
                                      store: TransactionStore) -> int:
        """Fetch transactions from NearBlocks API with rate limiting."""
        total_saved = 0
        page = 1
        per_page = 25  # NearBlocks limit
        
        while True:
            try:
                # Heavy rate limiting for NearBlocks free tier
                await asyncio.sleep(3)  # 3 second delay between requests
                
                url = f"https://api.nearblocks.io/v1/account/{account_id}/txns"
                params = {'page': page, 'per_page': per_page, 'order': 'desc'}
                
                async with self.session.get(url, params=params) as r:
                    if r.status == 429:
                        log.warning("  Rate limited, waiting 30s...")
                        await asyncio.sleep(30)
                        continue
                    
                    if r.status != 200:
                        log.error(f"  NearBlocks API error: {r.status}")
                        break
                    
                    data = await r.json()
                    txns = data.get('txns', [])
                    
                    if not txns:
                        break
                    
                    # Convert and save
                    converted = []
                    for tx in txns:
                        converted.append({
                            'hash': tx.get('transaction_hash'),
                            'block_height': tx.get('included_in_block_hash'),
                            'timestamp': tx.get('block_timestamp'),
                            'tx_type': tx.get('actions', [{}])[0].get('action', 'transfer') if tx.get('actions') else 'transfer',
                            'from_account': tx.get('signer_account_id'),
                            'to_account': tx.get('receiver_account_id'),
                            'amount': None,  # Would need to parse actions
                            'token': 'NEAR',
                            'raw': tx
                        })
                    
                    saved = store.save_transactions_batch(wallet_id, converted)
                    total_saved += saved
                    
                    log.info(f"  Page {page}: {len(txns)} txns, {saved} new")
                    
                    # Check if there are more pages
                    if len(txns) < per_page:
                        break
                    
                    page += 1
                    
                    # Safety limit
                    if page > 100:
                        log.warning("  Hit page limit (100), stopping")
                        break
                        
            except Exception as e:
                log.error(f"  Error fetching page {page}: {e}")
                break
        
        log.info(f"  Total saved: {total_saved} transactions")
        return total_saved


class RealtimeMonitor:
    """
    Monitors new blocks in real-time and checks for transactions
    involving ANY tracked wallet.
    
    This is the shared component that scales to many wallets without
    re-scanning the chain.
    """
    
    def __init__(self, registry: WalletRegistry, store: TransactionStore,
                 session: aiohttp.ClientSession):
        self.registry = registry
        self.store = store
        self.session = session
        self.shutdown = False
        self.last_block = 0
        self.stats = {'blocks': 0, 'txs_found': 0, 'start': time.time()}
        
        signal.signal(signal.SIGINT, lambda s,f: setattr(self, 'shutdown', True))
        signal.signal(signal.SIGTERM, lambda s,f: setattr(self, 'shutdown', True))
    
    async def get_current_block(self) -> int:
        """Get current finalized block height."""
        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.get(
                    f"{NEARDATA}/v0/last_block/final",
                    allow_redirects=True
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data['block']['header']['height']
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                log.debug(f"Error getting current block: {e}")
                await asyncio.sleep(2 ** attempt)
        return self.last_block or 187000000  # Fallback
    
    async def fetch_block(self, height: int) -> Optional[Dict]:
        """Fetch a block from NEARDATA."""
        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.get(f"{NEARDATA}/v0/block/{height}") as r:
                    if r.status == 200:
                        text = await r.text()
                        return json.loads(text) if text and text != 'null' else None
                    elif r.status == 429:
                        await asyncio.sleep(2 ** attempt)
            except Exception:
                await asyncio.sleep(1)
        return None
    
    def extract_wallet_transactions(self, block: Dict, wallets: Set[str]) -> List[Dict]:
        """Extract transactions involving any tracked wallet."""
        if not block:
            return []
        
        txs = []
        height = block.get('block', {}).get('header', {}).get('height', 0)
        ts = block.get('block', {}).get('header', {}).get('timestamp', 0)
        if ts:
            ts = datetime.fromtimestamp(ts // 1_000_000_000, timezone.utc).isoformat()
        
        seen = set()
        
        for shard in block.get('shards', []):
            chunk = shard.get('chunk')
            if not chunk:
                continue
            
            # Direct transactions
            for tx in chunk.get('transactions', []):
                txd = tx.get('transaction', {})
                h = txd.get('hash', '')
                if h in seen:
                    continue
                
                signer = txd.get('signer_id', '').lower()
                receiver = txd.get('receiver_id', '').lower()
                
                # Check if either party is a tracked wallet
                matched_wallet = None
                if signer in wallets:
                    matched_wallet = signer
                elif receiver in wallets:
                    matched_wallet = receiver
                
                if matched_wallet:
                    seen.add(h)
                    txs.append({
                        'hash': h,
                        'block_height': height,
                        'timestamp': ts,
                        'from_account': txd.get('signer_id', ''),
                        'to_account': txd.get('receiver_id', ''),
                        'matched_wallet': matched_wallet,
                        'raw': tx
                    })
            
            # Receipt outcomes
            for ro in shard.get('receipt_execution_outcomes', []):
                rcpt = ro.get('receipt', {})
                h = ro.get('tx_hash', '')
                if not h or h in seen:
                    continue
                
                pred = rcpt.get('predecessor_id', '').lower()
                recv = rcpt.get('receiver_id', '').lower()
                
                matched_wallet = None
                if pred in wallets:
                    matched_wallet = pred
                elif recv in wallets:
                    matched_wallet = recv
                
                if matched_wallet:
                    seen.add(h)
                    txs.append({
                        'hash': h,
                        'block_height': height,
                        'timestamp': ts,
                        'from_account': rcpt.get('predecessor_id', ''),
                        'to_account': rcpt.get('receiver_id', ''),
                        'matched_wallet': matched_wallet,
                        'raw': ro
                    })
        
        return txs
    
    def save_state(self):
        """Save monitor state for resume."""
        with open(STATE_PATH, 'w') as f:
            json.dump({
                'last_block': self.last_block,
                'stats': self.stats,
                'updated': datetime.now(timezone.utc).isoformat()
            }, f)
    
    def load_state(self) -> int:
        """Load last processed block from state."""
        if STATE_PATH.exists():
            try:
                with open(STATE_PATH) as f:
                    data = json.load(f)
                    return data.get('last_block', 0)
            except Exception:
                pass
        return 0
    
    async def run(self, start_block: int = None):
        """Run the real-time monitor."""
        log.info("Starting real-time monitor...")
        
        # Determine start block
        if start_block:
            self.last_block = start_block
        else:
            saved_block = self.load_state()
            if saved_block:
                self.last_block = saved_block
                log.info(f"Resuming from block {self.last_block}")
            else:
                self.last_block = await self.get_current_block() - 10
                log.info(f"Starting from recent block {self.last_block}")
        
        while not self.shutdown:
            try:
                # Get all tracked wallets (refreshes cache periodically)
                wallets = self.registry.get_all_wallets()
                
                if not wallets:
                    log.debug("No wallets to track, waiting...")
                    await asyncio.sleep(10)
                    continue
                
                # Get current block
                current = await self.get_current_block()
                
                # Process new blocks
                while self.last_block < current and not self.shutdown:
                    self.last_block += 1
                    
                    block = await self.fetch_block(self.last_block)
                    if block:
                        txs = self.extract_wallet_transactions(block, wallets)
                        
                        if txs:
                            for tx in txs:
                                wallet_id = self.store.get_wallet_id(tx['matched_wallet'])
                                if wallet_id:
                                    if self.store.save_transaction(wallet_id, tx):
                                        self.stats['txs_found'] += 1
                                        log.info(f"Block {self.last_block}: TX {tx['hash'][:12]}... "
                                                f"| {tx['from_account'][:15]} → {tx['to_account'][:15]}")
                    
                    self.stats['blocks'] += 1
                    
                    # Progress log every 100 blocks
                    if self.stats['blocks'] % 100 == 0:
                        elapsed = time.time() - self.stats['start']
                        rate = self.stats['blocks'] / elapsed if elapsed > 0 else 0
                        log.info(f"Progress: Block {self.last_block}, "
                                f"{self.stats['txs_found']} txs found, "
                                f"{rate:.1f} blk/s, "
                                f"tracking {len(wallets)} wallets")
                        self.save_state()
                
                # Wait for next block
                await asyncio.sleep(REALTIME_POLL_INTERVAL)
                
            except Exception as e:
                log.error(f"Error in monitor: {e}")
                await asyncio.sleep(5)
        
        self.save_state()
        log.info(f"Monitor stopped. Processed {self.stats['blocks']} blocks, "
                f"found {self.stats['txs_found']} transactions")


async def backfill_wallet(account_id: str):
    """Backfill a single wallet's transaction history."""
    async with aiohttp.ClientSession() as session:
        store = TransactionStore(DB_PATH)
        fetcher = WalletHistoryFetcher(session)
        
        wallet_id = store.get_wallet_id(account_id)
        if not wallet_id:
            log.error(f"Wallet {account_id} not found in database. Add it first with --add-wallet")
            return
        
        registry = WalletRegistry(DB_PATH)
        registry.update_sync_status(wallet_id, 'syncing')
        
        try:
            total = await fetcher.fetch_history(account_id, wallet_id, store)
            registry.update_sync_status(wallet_id, 'complete', total)
            log.info(f"Backfill complete: {total} transactions")
        except Exception as e:
            registry.update_sync_status(wallet_id, 'error')
            log.error(f"Backfill failed: {e}")


async def run_realtime():
    """Run the real-time monitor."""
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        registry = WalletRegistry(DB_PATH)
        store = TransactionStore(DB_PATH)
        monitor = RealtimeMonitor(registry, store, session)
        await monitor.run()


def add_wallet(account_id: str, user_id: int):
    """Add a wallet to the system."""
    registry = WalletRegistry(DB_PATH)
    wallet_id = registry.add_wallet(account_id, user_id)
    log.info(f"Wallet added with ID {wallet_id}")
    return wallet_id


async def main():
    parser = argparse.ArgumentParser(description='NearTax Hybrid Indexer')
    parser.add_argument('--backfill', type=str, help='Backfill history for a wallet')
    parser.add_argument('--realtime', action='store_true', help='Run real-time monitor')
    parser.add_argument('--add-wallet', type=str, help='Add a new wallet')
    parser.add_argument('--user-id', type=int, default=1, help='User ID for new wallet')
    
    args = parser.parse_args()
    
    if args.add_wallet:
        add_wallet(args.add_wallet, args.user_id)
        if args.backfill is None:
            # Auto-backfill after adding
            args.backfill = args.add_wallet
    
    if args.backfill:
        await backfill_wallet(args.backfill)
    elif args.realtime:
        await run_realtime()
    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
