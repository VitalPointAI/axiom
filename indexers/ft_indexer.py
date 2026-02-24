#!/usr/bin/env python3
"""
FT (Fungible Token) transaction indexer for NearTax.
Indexes all FT transfers for tracked wallets using NearBlocks API.
"""

import os
import time
import requests
from pathlib import Path
from decimal import Decimal
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.init import get_connection

# API Configuration
NEARBLOCKS_BASE = "https://api.nearblocks.io/v1"
NEARBLOCKS_API_KEY = getattr(config, 'NEARBLOCKS_API_KEY', None) or os.environ.get("NEARBLOCKS_API_KEY")
RATE_LIMIT_DELAY = getattr(config, 'RATE_LIMIT_DELAY', 1.0)


def get_headers():
    """Get API headers with auth."""
    headers = {}
    if NEARBLOCKS_API_KEY:
        headers["Authorization"] = f"Bearer {NEARBLOCKS_API_KEY}"
    return headers


def create_ft_tables():
    """Create FT transactions table."""
    conn = get_connection()
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ft_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            token_contract TEXT NOT NULL,
            token_symbol TEXT,
            token_name TEXT,
            token_decimals INTEGER DEFAULT 18,
            amount TEXT NOT NULL,
            counterparty TEXT,
            direction TEXT CHECK(direction IN ('in', 'out')),
            cause TEXT,
            tx_hash TEXT NOT NULL,
            block_height INTEGER,
            block_timestamp INTEGER,
            price_usd REAL,
            value_usd REAL,
            event_index TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_index),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    
    # Indexing progress for FT transactions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ft_indexing_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER UNIQUE NOT NULL,
            last_cursor TEXT,
            total_fetched INTEGER DEFAULT 0,
            total_expected INTEGER,
            status TEXT CHECK(status IN ('pending', 'in_progress', 'complete', 'error')),
            error_message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_wallet ON ft_transactions(wallet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_contract ON ft_transactions(token_contract)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_symbol ON ft_transactions(token_symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_timestamp ON ft_transactions(block_timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_direction ON ft_transactions(direction)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ft_tx_hash ON ft_transactions(tx_hash)")
    
    conn.commit()
    conn.close()
    print("FT tables created/verified")


def fetch_ft_txns_count(account_id: str) -> int:
    """Get total FT transaction count for an account."""
    url = f"{NEARBLOCKS_BASE}/account/{account_id}/ft-txns/count"
    
    resp = requests.get(url, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    return int(data.get("txns", [{}])[0].get("count", 0))


def fetch_ft_txns(account_id: str, cursor: str = None, per_page: int = 25) -> dict:
    """Fetch one page of FT transactions."""
    url = f"{NEARBLOCKS_BASE}/account/{account_id}/ft-txns"
    params = {"per_page": per_page}
    if cursor:
        params["cursor"] = cursor
    
    resp = requests.get(url, headers=get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_ft_indexing_status(wallet_id: int) -> dict:
    """Get current FT indexing progress."""
    conn = get_connection()
    row = conn.execute(
        """SELECT last_cursor, total_fetched, total_expected, status 
           FROM ft_indexing_progress WHERE wallet_id = ?""",
        (wallet_id,)
    ).fetchone()
    conn.close()
    
    if row:
        return {
            "cursor": row[0],
            "fetched": row[1] or 0,
            "expected": row[2],
            "status": row[3]
        }
    return {"cursor": None, "fetched": 0, "expected": None, "status": "pending"}


def update_ft_progress(wallet_id: int, cursor: str, fetched: int, status: str, 
                       expected: int = None, error: str = None):
    """Update FT indexing progress."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO ft_indexing_progress 
            (wallet_id, last_cursor, total_fetched, total_expected, status, error_message, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(wallet_id) DO UPDATE SET
            last_cursor = excluded.last_cursor,
            total_fetched = excluded.total_fetched,
            total_expected = COALESCE(excluded.total_expected, ft_indexing_progress.total_expected),
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = CURRENT_TIMESTAMP,
            completed_at = CASE WHEN excluded.status = 'complete' THEN CURRENT_TIMESTAMP ELSE completed_at END
    """, (wallet_id, cursor, fetched, expected, status, error))
    conn.commit()
    conn.close()


def parse_ft_transaction(tx: dict, account_id: str, wallet_id: int) -> dict | None:
    """Parse an FT transaction from NearBlocks API response."""
    ft_info = tx.get("ft", {})
    if not ft_info:
        return None
    
    # Determine direction based on delta_amount
    delta = tx.get("delta_amount", "0")
    try:
        delta_int = int(delta)
    except (ValueError, TypeError):
        delta_int = 0
    
    if delta_int > 0:
        direction = "in"
        amount = str(delta_int)
    else:
        direction = "out"
        amount = str(abs(delta_int))
    
    # Counterparty
    involved = tx.get("involved_account_id", "")
    
    return {
        "wallet_id": wallet_id,
        "token_contract": ft_info.get("contract", ""),
        "token_symbol": ft_info.get("symbol", ""),
        "token_name": ft_info.get("name", ""),
        "token_decimals": ft_info.get("decimals", 18),
        "amount": amount,
        "counterparty": involved,
        "direction": direction,
        "cause": tx.get("cause", ""),
        "tx_hash": tx.get("transaction_hash", ""),
        "block_height": tx.get("block", {}).get("block_height"),
        "block_timestamp": tx.get("block_timestamp"),
        "event_index": tx.get("event_index"),
    }


def index_wallet_ft(wallet_id: int, account_id: str, force: bool = False) -> int:
    """
    Index all FT transactions for a wallet.
    Resumable - saves cursor after each page.
    """
    # Get current status
    status = get_ft_indexing_status(wallet_id)
    
    if status["status"] == "complete" and not force:
        # Check for new transactions
        try:
            time.sleep(RATE_LIMIT_DELAY)
            current_count = fetch_ft_txns_count(account_id)
            if current_count <= status["fetched"]:
                print(f"  {account_id}: Already complete, no new FT txs ({status['fetched']})")
                return status["fetched"]
            print(f"  {account_id}: Found {current_count - status['fetched']} new FT txs")
            status["cursor"] = None
            status["fetched"] = 0
        except Exception as e:
            print(f"  {account_id}: Error checking for new FT txs - {e}")
            return status["fetched"]
    
    # Get total count
    try:
        time.sleep(RATE_LIMIT_DELAY)
        total_expected = fetch_ft_txns_count(account_id)
    except Exception as e:
        print(f"  {account_id}: Error getting FT tx count - {e}")
        total_expected = status.get("expected") or 0
    
    if total_expected == 0:
        print(f"  {account_id}: No FT transactions")
        update_ft_progress(wallet_id, None, 0, "complete", 0)
        return 0
    
    print(f"  {account_id}: {total_expected} FT transactions")
    
    cursor = status["cursor"]
    fetched = status["fetched"]
    
    update_ft_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
    
    conn = get_connection()
    
    try:
        while True:
            time.sleep(RATE_LIMIT_DELAY)
            result = fetch_ft_txns(account_id, cursor=cursor, per_page=25)
            txns = result.get("txns", [])
            
            if not txns:
                break
            
            for tx in txns:
                parsed = parse_ft_transaction(tx, account_id, wallet_id)
                if not parsed:
                    continue
                
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO ft_transactions 
                        (wallet_id, token_contract, token_symbol, token_name, token_decimals,
                         amount, counterparty, direction, cause, tx_hash, 
                         block_height, block_timestamp, event_index)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        parsed["wallet_id"],
                        parsed["token_contract"],
                        parsed["token_symbol"],
                        parsed["token_name"],
                        parsed["token_decimals"],
                        parsed["amount"],
                        parsed["counterparty"],
                        parsed["direction"],
                        parsed["cause"],
                        parsed["tx_hash"],
                        parsed["block_height"],
                        parsed["block_timestamp"],
                        parsed["event_index"],
                    ))
                except Exception as e:
                    print(f"    Warning: Error inserting FT tx: {e}")
            
            conn.commit()
            
            fetched += len(txns)
            cursor = result.get("cursor")
            
            update_ft_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
            
            # Progress display
            if total_expected > 0:
                pct = fetched / total_expected * 100
                print(f"    Progress: {fetched}/{total_expected} ({pct:.1f}%)")
            
            if not cursor:
                break
        
        update_ft_progress(wallet_id, None, fetched, "complete", total_expected)
        print(f"  {account_id}: Complete! {fetched} FT transactions indexed")
        return fetched
        
    except KeyboardInterrupt:
        print(f"\n  {account_id}: Interrupted at {fetched} FT txs. Progress saved.")
        update_ft_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
        conn.close()
        raise
    except Exception as e:
        update_ft_progress(wallet_id, cursor, fetched, "error", total_expected, str(e))
        print(f"  {account_id}: Error at {fetched} FT txs - {e}")
        conn.close()
        raise
    finally:
        conn.close()


def index_all_ft(force: bool = False):
    """Index FT transactions for all wallets."""
    create_ft_tables()
    
    conn = get_connection()
    wallets = conn.execute("SELECT id, account_id FROM wallets").fetchall()
    conn.close()
    
    print(f"Indexing FT transactions for {len(wallets)} wallets...")
    print(f"API Key: {'✓ present' if NEARBLOCKS_API_KEY else '✗ missing (will be rate limited)'}")
    print(f"Rate limit delay: {RATE_LIMIT_DELAY}s")
    print("-" * 50)
    
    total_txns = 0
    tokens_seen = set()
    
    for wallet_id, account_id in wallets:
        try:
            count = index_wallet_ft(wallet_id, account_id, force=force)
            total_txns += count
            time.sleep(RATE_LIMIT_DELAY)  # Extra delay between wallets
        except KeyboardInterrupt:
            print("\nInterrupted - progress saved")
            break
        except Exception as e:
            print(f"  Error: {e}")
            continue
    
    print("-" * 50)
    print(f"Done! Total FT transactions indexed: {total_txns}")
    
    # Summary of tokens found
    print_token_summary()
    
    return total_txns


def print_token_summary():
    """Print summary of all tokens found."""
    conn = get_connection()
    
    summary = conn.execute("""
        SELECT 
            token_symbol,
            token_name,
            token_contract,
            token_decimals,
            COUNT(*) as tx_count,
            COUNT(DISTINCT wallet_id) as wallet_count,
            SUM(CASE WHEN direction = 'in' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN direction = 'out' THEN 1 ELSE 0 END) as outbound
        FROM ft_transactions
        GROUP BY token_contract
        ORDER BY tx_count DESC
    """).fetchall()
    
    conn.close()
    
    if not summary:
        print("\nNo FT transactions found.")
        return
    
    print("\n" + "=" * 60)
    print("TOKEN SUMMARY")
    print("=" * 60)
    
    for row in summary:
        symbol, name, contract, decimals, tx_count, wallet_count, inbound, outbound = row
        print(f"\n{symbol} ({name})")
        print(f"  Contract: {contract[:20]}...")
        print(f"  Decimals: {decimals}")
        print(f"  Transactions: {tx_count} ({inbound} in, {outbound} out)")
        print(f"  Wallets: {wallet_count}")
    
    print("\n" + "=" * 60)


def get_ft_transactions_for_wallet(wallet_id: int = None, account_id: str = None):
    """Get FT transactions for a specific wallet."""
    conn = get_connection()
    
    if account_id and not wallet_id:
        row = conn.execute(
            "SELECT id FROM wallets WHERE account_id = ?", (account_id,)
        ).fetchone()
        if row:
            wallet_id = row[0]
    
    query = """
        SELECT 
            ft.token_symbol,
            ft.token_name,
            ft.amount,
            ft.token_decimals,
            ft.direction,
            ft.counterparty,
            ft.tx_hash,
            ft.block_timestamp,
            ft.price_usd,
            ft.value_usd,
            w.account_id
        FROM ft_transactions ft
        JOIN wallets w ON ft.wallet_id = w.id
    """
    
    if wallet_id:
        query += f" WHERE ft.wallet_id = {wallet_id}"
    
    query += " ORDER BY ft.block_timestamp DESC"
    
    txns = conn.execute(query).fetchall()
    conn.close()
    
    return txns


def get_defi_activity_summary():
    """Analyze DeFi activity based on counterparties."""
    conn = get_connection()
    
    # Common DeFi contract patterns
    defi_patterns = conn.execute("""
        SELECT 
            CASE 
                WHEN counterparty LIKE '%burrow%' THEN 'Burrow (Lending)'
                WHEN counterparty LIKE '%ref-finance%' OR counterparty LIKE '%v2.ref%' THEN 'Ref Finance (DEX)'
                WHEN counterparty LIKE '%aurora%' THEN 'Aurora'
                WHEN counterparty LIKE '%meta-pool%' OR counterparty LIKE '%linear%' THEN 'Liquid Staking'
                WHEN counterparty LIKE '%jumbo%' THEN 'Jumbo DEX'
                WHEN counterparty LIKE '%tonic%' THEN 'Tonic DEX'
                WHEN counterparty LIKE '%orderly%' THEN 'Orderly (Perps)'
                WHEN counterparty LIKE '%spin%' THEN 'Spin Finance'
                WHEN counterparty LIKE '%paras%' THEN 'Paras (NFT)'
                WHEN counterparty LIKE '%mintbase%' THEN 'Mintbase (NFT)'
                ELSE 'Other'
            END as protocol,
            token_symbol,
            direction,
            COUNT(*) as tx_count,
            COUNT(DISTINCT wallet_id) as wallets
        FROM ft_transactions
        GROUP BY protocol, token_symbol, direction
        ORDER BY tx_count DESC
    """).fetchall()
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("DEFI ACTIVITY SUMMARY")
    print("=" * 60)
    
    for row in defi_patterns[:20]:
        protocol, token, direction, count, wallets = row
        arrow = "→" if direction == "out" else "←"
        print(f"{protocol}: {token} {arrow} {count} txs ({wallets} wallets)")
    
    return defi_patterns


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FT Transaction Indexer")
    parser.add_argument("--force", action="store_true", help="Force re-index all wallets")
    parser.add_argument("--summary", action="store_true", help="Print token summary only")
    parser.add_argument("--defi", action="store_true", help="Print DeFi activity summary")
    parser.add_argument("--wallet", type=str, help="Index specific wallet only")
    
    args = parser.parse_args()
    
    if args.summary:
        print_token_summary()
    elif args.defi:
        get_defi_activity_summary()
    elif args.wallet:
        create_ft_tables()
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM wallets WHERE account_id = ?", (args.wallet,)
        ).fetchone()
        conn.close()
        
        if row:
            index_wallet_ft(row[0], args.wallet, force=args.force)
        else:
            print(f"Wallet not found: {args.wallet}")
    else:
        index_all_ft(force=args.force)
