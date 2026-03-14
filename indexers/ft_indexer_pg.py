#!/usr/bin/env python3
"""
FT (Fungible Token) transaction indexer for NearTax (PostgreSQL version).
Properly captures:
- Direction (in/out based on delta_amount sign)
- Counterparty (involved_account_id)
- Cause (MINT, BURN, TRANSFER)
- Event index (for deduplication)
- Human-readable amounts
"""

import os
import time
import requests
import psycopg2
from decimal import Decimal, ROUND_DOWN

# Configuration
NEARBLOCKS_BASE = "https://api.nearblocks.io/v1"
NEARBLOCKS_API_KEY = os.environ.get("NEARBLOCKS_API_KEY", "")
RATE_LIMIT_DELAY = 2.0  # seconds between requests

# Database connection
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "postgres://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax"
)


def get_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def get_headers():
    """Get API headers with auth."""
    headers = {"User-Agent": "NearTax-Indexer/1.0"}
    if NEARBLOCKS_API_KEY:
        headers["Authorization"] = f"Bearer {NEARBLOCKS_API_KEY}"
    return headers


def fetch_ft_txns(account_id: str, cursor: str = None, per_page: int = 25) -> dict:
    """Fetch one page of FT transactions from NearBlocks."""
    url = f"{NEARBLOCKS_BASE}/account/{account_id}/ft-txns"
    params = {"per_page": per_page}
    if cursor:
        params["cursor"] = cursor
    
    resp = requests.get(url, headers=get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_ft_txns_count(account_id: str) -> int:
    """Get total FT transaction count for an account."""
    url = f"{NEARBLOCKS_BASE}/account/{account_id}/ft-txns/count"
    resp = requests.get(url, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return int(data.get("txns", [{}])[0].get("count", 0))


def parse_ft_transaction(tx: dict, wallet_id: int) -> dict | None:
    """
    Parse an FT transaction from NearBlocks API response.
    Returns dict with all fields properly formatted.
    """
    ft_info = tx.get("ft", {})
    if not ft_info:
        return None
    
    # Get delta amount - THIS IS KEY
    delta = tx.get("delta_amount")
    if delta is None:
        return None
    
    try:
        delta_int = int(delta)
    except (ValueError, TypeError):
        return None
    
    if delta_int == 0:
        return None
    
    # Direction based on delta sign
    if delta_int > 0:
        direction = "in"
        raw_amount = delta_int
    else:
        direction = "out"
        raw_amount = abs(delta_int)
    
    # Get decimals and convert to human-readable
    decimals = ft_info.get("decimals", 18)
    try:
        human_amount = Decimal(raw_amount) / Decimal(10 ** decimals)
        # Round to reasonable precision
        human_amount = human_amount.quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
    except Exception:
        human_amount = Decimal(raw_amount)
    
    # Counterparty - very important for tax tracking
    counterparty = tx.get("involved_account_id") or ""
    
    # Cause - MINT, BURN, TRANSFER
    cause = tx.get("cause", "TRANSFER")
    
    # Event index - CRITICAL for deduplication
    event_index = tx.get("event_index")
    if not event_index:
        # Generate a unique index if missing
        event_index = f"{tx.get('transaction_hash', 'unknown')}_{tx.get('block_timestamp', 0)}_{direction}_{raw_amount}"
    
    return {
        "wallet_id": wallet_id,
        "token_contract": ft_info.get("contract", ""),
        "token_symbol": ft_info.get("symbol", ""),
        "token_name": ft_info.get("name", ""),
        "token_decimals": decimals,
        "amount": str(human_amount),
        "counterparty": counterparty,
        "direction": direction,
        "cause": cause,
        "tx_hash": tx.get("transaction_hash", ""),
        "block_height": tx.get("block", {}).get("block_height"),
        "block_timestamp": tx.get("block_timestamp"),
        "event_index": event_index,
    }


def delete_wallet_ft_transactions(conn, wallet_id: int, token_contract: str = None):
    """Delete existing FT transactions for a wallet (optionally filtered by token)."""
    cur = conn.cursor()
    if token_contract:
        cur.execute(
            "DELETE FROM ft_transactions WHERE wallet_id = %s AND token_contract = %s",
            (wallet_id, token_contract)
        )
    else:
        cur.execute(
            "DELETE FROM ft_transactions WHERE wallet_id = %s",
            (wallet_id,)
        )
    deleted = cur.rowcount
    conn.commit()
    return deleted


def index_wallet_ft(wallet_id: int, account_id: str, force: bool = False, 
                    token_filter: str = None, user_id: int = None) -> int:
    """
    Index all FT transactions for a wallet.
    
    Args:
        wallet_id: Database wallet ID
        account_id: NEAR account account_id
        force: If True, delete existing and re-index
        token_filter: Optional - only index specific token contract
        user_id: Optional - verify wallet belongs to user
    
    Returns:
        Number of transactions indexed
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Verify wallet ownership if user_id provided
    if user_id:
        cur.execute("SELECT id FROM wallets WHERE id = %s AND user_id = %s", (wallet_id, user_id))
        if not cur.fetchone():
            print(f"  Error: Wallet {wallet_id} does not belong to user {user_id}")
            conn.close()
            return 0
    
    # Get current count
    if token_filter:
        cur.execute(
            "SELECT COUNT(*) FROM ft_transactions WHERE wallet_id = %s AND token_contract = %s",
            (wallet_id, token_filter)
        )
    else:
        cur.execute(
            "SELECT COUNT(*) FROM ft_transactions WHERE wallet_id = %s",
            (wallet_id,)
        )
    existing_count = cur.fetchone()[0]
    
    # Force re-index?
    if force and existing_count > 0:
        deleted = delete_wallet_ft_transactions(conn, wallet_id, token_filter)
        print(f"  Deleted {deleted} existing FT transactions")
    
    print(f"  Indexing FT transactions for {account_id}...")
    
    try:
        time.sleep(RATE_LIMIT_DELAY)
        total_expected = fetch_ft_txns_count(account_id)
        print(f"  Total FT transactions on chain: {total_expected}")
    except Exception as e:
        print(f"  Error getting count: {e}")
        conn.close()
        return 0
    
    if total_expected == 0:
        print("  No FT transactions found")
        conn.close()
        return 0
    
    cursor = None
    fetched = 0
    inserted = 0
    skipped = 0
    
    try:
        while True:
            time.sleep(RATE_LIMIT_DELAY)
            result = fetch_ft_txns(account_id, cursor=cursor, per_page=25)
            txns = result.get("txns", [])
            
            if not txns:
                break
            
            for tx in txns:
                # Filter by token if specified
                ft_info = tx.get("ft", {})
                if token_filter and ft_info.get("contract") != token_filter:
                    continue
                
                parsed = parse_ft_transaction(tx, wallet_id)
                if not parsed:
                    continue
                
                # Check if already exists
                cur.execute(
                    "SELECT 1 FROM ft_transactions WHERE event_index = %s",
                    (parsed["event_index"],)
                )
                if cur.fetchone():
                    skipped += 1
                    continue
                
                # Insert transaction
                try:
                    cur.execute("""
                        INSERT INTO ft_transactions 
                        (wallet_id, token_contract, token_symbol, token_name, token_decimals,
                         amount, counterparty, direction, cause, tx_hash, 
                         block_height, block_timestamp, event_index)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    inserted += 1
                except psycopg2.IntegrityError:
                    conn.rollback()
                    skipped += 1
                except Exception as e:
                    print(f"    Error inserting: {e}")
                    conn.rollback()
            
            conn.commit()
            fetched += len(txns)
            
            # Progress
            pct = fetched / total_expected * 100 if total_expected > 0 else 0
            print(f"    Progress: {fetched}/{total_expected} ({pct:.1f}%) - {inserted} new, {skipped} skipped")
            
            cursor = result.get("cursor")
            if not cursor:
                break
        
        print(f"  Complete! {inserted} new transactions indexed, {skipped} skipped")
        return inserted
        
    except KeyboardInterrupt:
        print(f"\n  Interrupted at {fetched} txs")
        conn.commit()
        raise
    except Exception as e:
        print(f"  Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def reindex_wallet(wallet_id: int = None, account_id: str = None, 
                   token_filter: str = None, user_id: int = None):
    """
    Re-index a specific wallet's FT transactions.
    
    Args:
        wallet_id: Database wallet ID (or lookup by account_id)
        account_id: NEAR account account_id
        token_filter: Optional - only reindex specific token
        user_id: Optional - verify wallet ownership
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Get wallet info
    if account_id and not wallet_id:
        if user_id:
            cur.execute(
                "SELECT id, account_id FROM wallets WHERE account_id = %s AND user_id = %s",
                (account_id, user_id)
            )
        else:
            cur.execute("SELECT id, account_id FROM wallets WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            print(f"Wallet not found: {account_id}")
            conn.close()
            return
        wallet_id, account_id = row
    elif wallet_id and not account_id:
        if user_id:
            cur.execute(
                "SELECT id, account_id FROM wallets WHERE id = %s AND user_id = %s",
                (wallet_id, user_id)
            )
        else:
            cur.execute("SELECT id, account_id FROM wallets WHERE id = %s", (wallet_id,))
        row = cur.fetchone()
        if not row:
            print(f"Wallet not found: {wallet_id}")
            conn.close()
            return
        wallet_id, account_id = row
    
    conn.close()
    
    print(f"Re-indexing wallet {wallet_id} ({account_id})")
    if token_filter:
        print(f"  Token filter: {token_filter}")
    
    return index_wallet_ft(wallet_id, account_id, force=True, 
                          token_filter=token_filter, user_id=user_id)


def index_all_wallets(user_id: int = None, force: bool = False):
    """
    Index FT transactions for all wallets (optionally filtered by user).
    """
    conn = get_connection()
    cur = conn.cursor()
    
    if user_id:
        cur.execute("SELECT id, account_id FROM wallets WHERE user_id = %s", (user_id,))
    else:
        cur.execute("SELECT id, account_id FROM wallets")
    
    wallets = cur.fetchall()
    conn.close()
    
    print(f"Indexing FT transactions for {len(wallets)} wallets...")
    print(f"API Key: {'✓ present' if NEARBLOCKS_API_KEY else '✗ missing (will be rate limited)'}")
    print("-" * 50)
    
    total = 0
    for wallet_id, account_id in wallets:
        try:
            count = index_wallet_ft(wallet_id, account_id, force=force, user_id=user_id)
            total += count
        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"  Error: {e}")
            continue
        
        # Extra delay between wallets
        time.sleep(RATE_LIMIT_DELAY * 2)
    
    print("-" * 50)
    print(f"Done! Total new FT transactions indexed: {total}")
    return total


def print_summary(user_id: int = None):
    """Print summary of FT transactions."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
        SELECT 
            ft.token_symbol,
            ft.token_contract,
            COUNT(*) as tx_count,
            SUM(CASE WHEN ft.direction = 'in' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN ft.direction = 'out' THEN 1 ELSE 0 END) as outbound,
            COUNT(DISTINCT ft.wallet_id) as wallets
        FROM ft_transactions ft
    """
    
    if user_id:
        query += """
            JOIN wallets w ON ft.wallet_id = w.id
            WHERE w.user_id = %s
        """
        query += " GROUP BY ft.token_symbol, ft.token_contract ORDER BY tx_count DESC"
        cur.execute(query, (user_id,))
    else:
        query += " GROUP BY ft.token_symbol, ft.token_contract ORDER BY tx_count DESC"
        cur.execute(query)
    
    rows = cur.fetchall()
    conn.close()
    
    print("\n" + "=" * 60)
    print("FT TRANSACTION SUMMARY")
    print("=" * 60)
    
    for symbol, contract, tx_count, inbound, outbound, wallets in rows:
        print(f"\n{symbol}")
        print(f"  Contract: {contract[:30]}...")
        print(f"  Transactions: {tx_count} ({inbound} in, {outbound} out)")
        print(f"  Wallets: {wallets}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FT Transaction Indexer (PostgreSQL)")
    parser.add_argument("--wallet", type=str, help="Index specific wallet (account_id)")
    parser.add_argument("--wallet-id", type=int, help="Index specific wallet (ID)")
    parser.add_argument("--user", type=int, help="Filter by user ID")
    parser.add_argument("--token", type=str, help="Filter by token contract")
    parser.add_argument("--force", action="store_true", help="Force re-index (delete existing)")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    parser.add_argument("--all", action="store_true", help="Index all wallets")
    
    args = parser.parse_args()
    
    if args.summary:
        print_summary(user_id=args.user)
    elif args.wallet or args.wallet_id:
        reindex_wallet(
            wallet_id=args.wallet_id,
            account_id=args.wallet,
            token_filter=args.token,
            user_id=args.user
        )
    elif args.all:
        index_all_wallets(user_id=args.user, force=args.force)
    else:
        parser.print_help()
