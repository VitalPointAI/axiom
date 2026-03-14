#!/usr/bin/env python3
"""
EVM Indexer using Alchemy API - V2
Captures ALL transactions including zero-value contract calls with proper gas fee tracking.
"""

import logging
import os
import sys
import json
import sqlite3
import requests
from typing import Optional, List, Dict, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

# Alchemy API configuration
ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
ALCHEMY_ETH_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
ALCHEMY_POLYGON_URL = f"https://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

DB_PATH = os.environ.get('NEARTAX_DB', '/home/deploy/neartax/neartax.db')

def get_db():
    return sqlite3.connect(DB_PATH)

def get_alchemy_url(chain: str) -> str:
    chain_lower = chain.lower()
    if chain_lower in ('ethereum', 'eth'):
        return ALCHEMY_ETH_URL
    elif chain_lower in ('polygon', 'matic'):
        return ALCHEMY_POLYGON_URL
    else:
        raise ValueError(f"Unsupported chain: {chain}")

def fetch_asset_transfers(chain: str, address: str, direction: str = 'both') -> List[Dict]:
    """
    Fetch ALL asset transfers using Alchemy's getAssetTransfers API.
    Key change: excludeZeroValue: False to capture contract calls without value.
    """
    url = get_alchemy_url(chain)
    all_transfers = []

    categories = ["external", "internal", "erc20"]

    for from_to in ['from', 'to'] if direction == 'both' else [direction]:
        page_key = None

        while True:
            params = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [{
                    from_to + "Address": address.lower(),
                    "category": categories,
                    "withMetadata": True,
                    "excludeZeroValue": False,  # KEY CHANGE: capture zero-value txs!
                    "maxCount": "0x3e8",
                }]
            }

            if page_key:
                params["params"][0]["pageKey"] = page_key

            try:
                response = requests.post(url, json=params, timeout=30)
                data = response.json()

                if "error" in data:
                    print(f"Alchemy API error: {data['error']}")
                    break

                result = data.get("result", {})
                transfers = result.get("transfers", [])
                all_transfers.extend(transfers)

                page_key = result.get("pageKey")
                if not page_key:
                    break

                print(f"  Fetched {len(transfers)} transfers, continuing...")

            except Exception as e:
                print(f"Error fetching transfers: {e}")
                break

    return all_transfers

def get_transaction_receipt(chain: str, tx_hash: str) -> Optional[Dict]:
    """Fetch transaction receipt to get gas used and effective gas price."""
    url = get_alchemy_url(chain)

    try:
        response = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash]
        }, timeout=10)

        data = response.json()
        return data.get("result")
    except Exception as e:
        print(f"Error fetching receipt for {tx_hash[:16]}: {e}")
        return None

def get_transaction(chain: str, tx_hash: str) -> Optional[Dict]:
    """Fetch transaction details to get 'from' address."""
    url = get_alchemy_url(chain)

    try:
        response = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionByHash",
            "params": [tx_hash]
        }, timeout=10)

        data = response.json()
        return data.get("result")
    except Exception as e:
        print(f"Error fetching tx {tx_hash[:16]}: {e}")
        return None

def batch_get_receipts(chain: str, tx_hashes: List[str]) -> Dict[str, Dict]:
    """Batch fetch receipts using JSON-RPC batch call."""
    url = get_alchemy_url(chain)
    receipts = {}

    # Process in batches of 100
    batch_size = 100
    for i in range(0, len(tx_hashes), batch_size):
        batch = tx_hashes[i:i+batch_size]

        requests_batch = [
            {
                "jsonrpc": "2.0",
                "id": idx,
                "method": "eth_getTransactionReceipt",
                "params": [tx_hash]
            }
            for idx, tx_hash in enumerate(batch)
        ]

        try:
            response = requests.post(url, json=requests_batch, timeout=60)
            results = response.json()

            for idx, result in enumerate(results):
                if "result" in result and result["result"]:
                    tx_hash = batch[idx]
                    receipts[tx_hash] = result["result"]
        except Exception as e:
            print(f"  Error batch fetching receipts: {e}")
            # Fall back to individual fetches
            for tx_hash in batch:
                receipt = get_transaction_receipt(chain, tx_hash)
                if receipt:
                    receipts[tx_hash] = receipt

    return receipts

def process_transfers_and_fees(transfers: List[Dict], wallet_address: str, chain: str) -> tuple:
    """
    Process transfers and extract both value transfers AND gas fees.
    Returns (value_transactions, fee_transactions)
    """
    wallet_lower = wallet_address.lower()
    value_txs = []

    # Group transfers by tx_hash to handle multi-transfer txs
    by_hash = defaultdict(list)
    for t in transfers:
        by_hash[t.get("hash", "")].append(t)

    # Track which tx_hashes WE sent (we pay the fee)
    our_sent_hashes: Set[str] = set()

    for tx_hash, tx_transfers in by_hash.items():
        for t in tx_transfers:
            from_addr = t.get("from", "").lower()
            to_addr = t.get("to", "").lower()

            # Determine direction
            if from_addr == wallet_lower:
                direction = "OUT"
                counterparty = to_addr
                our_sent_hashes.add(tx_hash)  # We sent this, we pay the fee
            elif to_addr == wallet_lower:
                direction = "IN"
                counterparty = from_addr
            else:
                continue  # Not related

            # Get value
            value = t.get("value")
            if value is None:
                raw_value = t.get("rawContract", {}).get("value")
                if raw_value:
                    try:
                        value = int(raw_value, 16) / 1e18
                    except (ValueError, TypeError) as e:
                        logger.warning("Failed to parse raw hex value %r for tx %s: %s", raw_value, t.get("hash", ""), e)
                        value = 0
                else:
                    value = 0

            # Get asset info
            asset = t.get("asset", "ETH")
            category = t.get("category", "external")

            # Map category to action type
            if category == "internal":
                action_type = "INTERNAL_TRANSFER"
            elif category == "erc20":
                action_type = "FT_TRANSFER"
            else:
                action_type = "TRANSFER"

            # Get timestamp from metadata
            block_timestamp = None
            metadata = t.get("metadata", {})
            if "blockTimestamp" in metadata:
                block_timestamp = metadata["blockTimestamp"]

            # Only skip if truly zero value AND not an ERC20 (ERC20 has its own value)
            if value == 0 and category != "erc20":
                continue

            value_txs.append({
                "tx_hash": tx_hash,
                "block_num": int(t.get("blockNum", "0x0"), 16),
                "timestamp": block_timestamp,
                "direction": direction,
                "counterparty": counterparty,
                "amount": value,
                "asset": asset,
                "action_type": action_type,
                "category": category,
            })

    return value_txs, list(our_sent_hashes)

def calculate_gas_fee(receipt: Dict) -> float:
    """Calculate gas fee from receipt."""
    gas_used = int(receipt.get("gasUsed", "0x0"), 16)

    # Try effectiveGasPrice first (EIP-1559), fall back to gasPrice
    effective_gas_price = receipt.get("effectiveGasPrice")
    if effective_gas_price:
        gas_price = int(effective_gas_price, 16)
    else:
        # For older transactions, we'd need to fetch the transaction itself
        # For now, estimate with a typical gas price
        gas_price = int(receipt.get("gasPrice", "0x0"), 16) if "gasPrice" in receipt else 0

    if gas_price == 0:
        return 0

    fee_wei = gas_used * gas_price
    fee_eth = fee_wei / 1e18
    return fee_eth

def index_wallet(wallet_id: int, address: str, chain: str) -> Dict[str, int]:
    """Index all transactions for a wallet using Alchemy with proper fee tracking."""

    print(f"Indexing {chain} wallet: {address[:10]}...")

    # Fetch all transfers (including zero-value)
    transfers = fetch_asset_transfers(chain, address)
    print(f"  Found {len(transfers)} total transfers")

    # Process transfers
    value_txs, our_sent_hashes = process_transfers_and_fees(transfers, address, chain)
    print(f"  {len(value_txs)} value transactions, {len(our_sent_hashes)} sent txs (we pay fees)")

    # Fetch receipts for transactions we sent (to get gas fees)
    print("  Fetching receipts for fee calculation...")
    receipts = batch_get_receipts(chain, our_sent_hashes)
    print(f"  Got {len(receipts)} receipts")

    # Create fee transactions
    fee_txs = []
    total_fees = 0
    for tx_hash in our_sent_hashes:
        receipt = receipts.get(tx_hash)
        if receipt:
            fee = calculate_gas_fee(receipt)
            if fee > 0:
                total_fees += fee

                # Get block info from receipt
                block_num = int(receipt.get("blockNumber", "0x0"), 16)

                # Find timestamp from value_txs or fetch it
                timestamp = None
                for vtx in value_txs:
                    if vtx["tx_hash"] == tx_hash:
                        timestamp = vtx.get("timestamp")
                        break

                # Determine native token based on chain
                chain_lower = chain.lower()
                native_token = "ETH" if chain_lower in ('ethereum', 'eth') else "MATIC"

                fee_txs.append({
                    "tx_hash": tx_hash,
                    "block_num": block_num,
                    "timestamp": timestamp,
                    "direction": "OUT",
                    "counterparty": "gas",
                    "amount": fee,
                    "asset": native_token,
                    "action_type": "FEE",
                    "category": "fee",
                })

    print(f"  Total gas fees: {total_fees:.6f} ETH across {len(fee_txs)} transactions")

    # Insert into database
    conn = get_db()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    fees_inserted = 0

    # Insert value transactions
    for tx in value_txs:
        try:
            # Convert ISO timestamp to Unix timestamp if present
            block_ts = None
            if tx.get("timestamp"):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00"))
                    block_ts = int(dt.timestamp() * 1_000_000_000)  # nanoseconds like NEAR
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse timestamp %r for tx %s: %s", tx.get("timestamp"), tx.get("tx_hash", ""), e)

            cursor.execute("""
                INSERT OR IGNORE INTO transactions
                (wallet_id, tx_hash, block_height, block_timestamp, action_type,
                 direction, counterparty, amount, asset, success, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet_id,
                tx["tx_hash"],
                tx["block_num"],
                block_ts,
                tx["action_type"],
                tx["direction"],
                tx["counterparty"],
                tx["amount"],
                tx["asset"],
                1,
                f"alchemy_{chain}"  # Track source
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        except Exception as e:
            print(f"  Error inserting tx {tx['tx_hash'][:16]}: {e}")
            skipped += 1

    # Insert fee transactions with unique hash suffix
    for tx in fee_txs:
        try:
            fee_hash = tx["tx_hash"] + "_fee"  # Make unique for fee entry

            # Convert ISO timestamp to Unix timestamp if present
            block_ts = None
            if tx.get("timestamp"):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00"))
                    block_ts = int(dt.timestamp() * 1_000_000_000)  # nanoseconds
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse timestamp %r for fee tx %s: %s", tx.get("timestamp"), tx.get("tx_hash", ""), e)

            cursor.execute("""
                INSERT OR IGNORE INTO transactions
                (wallet_id, tx_hash, block_height, block_timestamp, action_type,
                 direction, counterparty, amount, asset, success, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet_id,
                fee_hash,
                tx["block_num"],
                block_ts,
                tx["action_type"],
                tx["direction"],
                tx["counterparty"],
                tx["amount"],
                tx["asset"],
                1,
                f"alchemy_{chain}"
            ))

            if cursor.rowcount > 0:
                fees_inserted += 1

        except Exception as e:
            print(f"  Error inserting fee for {tx['tx_hash'][:16]}: {e}")

    conn.commit()
    conn.close()

    print(f"  Inserted: {inserted} transfers, {fees_inserted} fees | Skipped: {skipped}")
    return {"inserted": inserted, "fees": fees_inserted, "skipped": skipped, "total_fees": total_fees}

def index_all_evm_wallets():
    """Index all EVM wallets in the database."""

    if not ALCHEMY_API_KEY:
        print("ERROR: ALCHEMY_API_KEY environment variable not set")
        print("Get a free key at: https://dashboard.alchemy.com/")
        sys.exit(1)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, account_id, chain FROM wallets
        WHERE chain IN ('ethereum', 'polygon', 'ETH', 'POLYGON', 'cronos', 'CRONOS')
    """)
    wallets = cursor.fetchall()
    conn.close()

    print(f"Found {len(wallets)} EVM wallets to index")

    total_inserted = 0
    total_fees = 0
    total_skipped = 0
    grand_total_fees = 0

    for wallet_id, address, chain in wallets:
        result = index_wallet(wallet_id, address, chain)
        total_inserted += result["inserted"]
        total_fees += result["fees"]
        total_skipped += result["skipped"]
        grand_total_fees += result["total_fees"]

    print(f"\n{'='*50}")
    print(f"Total: {total_inserted} transfers, {total_fees} fees inserted")
    print(f"Total gas fees tracked: {grand_total_fees:.6f} ETH")
    print(f"Skipped (duplicates): {total_skipped}")

def verify_wallet_balance(address: str, chain: str) -> Dict:
    """Verify wallet balance matches computed from transactions."""

    url = get_alchemy_url(chain)

    # Get on-chain balance
    response = requests.post(url, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBalance",
        "params": [address, "latest"]
    })

    data = response.json()
    on_chain = int(data.get("result", "0x0"), 16) / 1e18

    # Compute from our transactions
    conn = get_db()
    cursor = conn.cursor()

    # Get native token only (ETH for ethereum, MATIC for polygon)
    chain_lower = chain.lower()
    native_token = "ETH" if chain_lower in ('ethereum', 'eth') else "MATIC"

    cursor.execute("""
        SELECT
            SUM(CASE WHEN direction = 'IN' THEN CAST(amount AS REAL) ELSE 0 END) as total_in,
            SUM(CASE WHEN direction = 'OUT' THEN CAST(amount AS REAL) ELSE 0 END) as total_out
        FROM transactions
        WHERE wallet_id = (SELECT id FROM wallets WHERE LOWER(account_id) = LOWER(?) AND LOWER(chain) = LOWER(?))
        AND (asset = ? OR asset IS NULL OR asset = '')
        AND action_type != 'FT_TRANSFER'
    """, (address, chain, native_token))

    row = cursor.fetchone()
    conn.close()

    total_in = row[0] or 0
    total_out = row[1] or 0
    computed = total_in - total_out

    diff = on_chain - computed

    return {
        "address": address,
        "chain": chain,
        "on_chain": round(on_chain, 6),
        "total_in": round(total_in, 6),
        "total_out": round(total_out, 6),
        "computed": round(computed, 6),
        "diff": round(diff, 6),
        "diff_usd_approx": round(diff * 4800, 2),  # Rough ETH price
        "match": abs(diff) < 0.01  # Within 0.01 ETH
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "verify" and len(sys.argv) >= 4:
            result = verify_wallet_balance(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2))
        elif sys.argv[1] == "index" and len(sys.argv) >= 4:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM wallets WHERE LOWER(account_id) = LOWER(?) AND LOWER(chain) = LOWER(?)",
                          (sys.argv[2], sys.argv[3]))
            row = cursor.fetchone()
            conn.close()
            if row:
                index_wallet(row[0], sys.argv[2], sys.argv[3])
            else:
                print(f"Wallet not found: {sys.argv[2]} on {sys.argv[3]}")
        else:
            print("Usage:")
            print("  python3 evm_indexer_alchemy.py           # Index all EVM wallets")
            print("  python3 evm_indexer_alchemy.py verify <address> <chain>")
            print("  python3 evm_indexer_alchemy.py index <address> <chain>")
    else:
        index_all_evm_wallets()

# ============ CRONOS SUPPORT ============
CRONOSCAN_API_KEY = 'n36C9DFXqwKqBkqwW1We0NUTCWvUewsi'
CRONOSCAN_URL = 'https://cronos.org/explorer/api'

def fetch_cronos_transactions(address: str) -> List[Dict]:
    """Fetch transactions from Cronos using Cronoscan API"""
    import requests

    all_txs = []

    # Normal transactions
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': 0,
        'endblock': 99999999,
        'sort': 'desc',
        'apikey': CRONOSCAN_API_KEY
    }

    try:
        resp = requests.get(CRONOSCAN_URL, params=params, timeout=30)
        data = resp.json()
        if data.get('status') == '1':
            all_txs.extend(data.get('result', []))
    except Exception as e:
        print(f'Cronos txlist error: {e}')

    # Token transfers
    params['action'] = 'tokentx'
    try:
        resp = requests.get(CRONOSCAN_URL, params=params, timeout=30)
        data = resp.json()
        if data.get('status') == '1':
            all_txs.extend(data.get('result', []))
    except Exception as e:
        print(f'Cronos tokentx error: {e}')

    return all_txs

def index_cronos_wallet(wallet_id: int, address: str) -> Dict:
    """Index a Cronos wallet using Cronoscan API"""
    print(f'Indexing Cronos wallet: {address[:12]}...')

    txs = fetch_cronos_transactions(address)
    if not txs:
        print('  No Cronos transactions found')
        return {'inserted': 0, 'skipped': 0}

    print(f'  Found {len(txs)} Cronos transactions')
    # TODO: Insert into evm_transactions with chain='cronos'
    return {'inserted': 0, 'skipped': 0, 'total': len(txs)}
