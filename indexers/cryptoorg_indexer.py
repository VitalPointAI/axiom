#!/usr/bin/env python3
"""
Crypto.org Chain Transaction Indexer
Uses the Crypto.org LCD API (Cosmos SDK) - handles cro1... addresses
"""

import time
import requests
import psycopg2
from typing import Optional, List, Dict
from decimal import Decimal
from datetime import datetime
import sys

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'

# Crypto.org Chain LCD endpoints
CRYPTOORG_LCD_ENDPOINTS = [
    'https://rest.mainnet.crypto.org',
    'https://rest.crypto.org',
]

RATE_LIMIT_DELAY = 0.5
MAX_RETRIES = 3
CRO_DECIMALS = 8  # 1 CRO = 100,000,000 basecro


def get_connection():
    return psycopg2.connect(PG_CONN)


class CryptoOrgIndexer:
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or CRYPTOORG_LCD_ENDPOINTS[0]
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _request(self, path: str, params: Dict = None, retries: int = 0) -> Dict:
        self._wait_for_rate_limit()
        url = f"{self.endpoint}{path}"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            if retries < MAX_RETRIES:
                if len(CRYPTOORG_LCD_ENDPOINTS) > 1:
                    endpoint_idx = (CRYPTOORG_LCD_ENDPOINTS.index(self.endpoint) + 1) % len(CRYPTOORG_LCD_ENDPOINTS)
                    self.endpoint = CRYPTOORG_LCD_ENDPOINTS[endpoint_idx]
                print(f"  Retry {retries+1}...")
                time.sleep(RATE_LIMIT_DELAY * (2 ** retries))
                return self._request(path, params, retries + 1)
            raise

    def get_account_balance(self, address: str) -> Dict[str, Decimal]:
        try:
            data = self._request(f'/cosmos/bank/v1beta1/balances/{address}')
            balances = {}
            for balance in data.get('balances', []):
                denom = balance.get('denom', 'basecro')
                amount = Decimal(balance.get('amount', '0'))
                if denom == 'basecro':
                    balances['CRO'] = amount / Decimal(10 ** CRO_DECIMALS)
                else:
                    balances[denom] = amount
            return balances
        except Exception as e:
            print(f"  Error getting balance: {e}")
            return {}

    def get_account_transactions(self, address: str, pagination_key: Optional[str] = None, limit: int = 100) -> Dict:
        params = {
            'events': f"message.sender='{address}'",
            'pagination.limit': str(limit),
            'order_by': 'ORDER_BY_DESC',
        }
        if pagination_key:
            params['pagination.key'] = pagination_key

        try:
            sent = self._request('/cosmos/tx/v1beta1/txs', params)
            params['events'] = f"transfer.recipient='{address}'"
            received = self._request('/cosmos/tx/v1beta1/txs', params)

            all_txs = {}
            for tx_resp in sent.get('tx_responses', []):
                all_txs[tx_resp.get('txhash', '')] = tx_resp
            for tx_resp in received.get('tx_responses', []):
                all_txs[tx_resp.get('txhash', '')] = tx_resp

            return {
                'tx_responses': list(all_txs.values()),
                'pagination': sent.get('pagination', {})
            }
        except Exception as e:
            print(f"  Error fetching transactions: {e}")
            return {'tx_responses': [], 'pagination': {}}

    def get_all_transactions(self, address: str, limit_pages: int = 50) -> List[Dict]:
        all_txs = []
        pagination_key = None
        page = 0

        while page < limit_pages:
            result = self.get_account_transactions(address, pagination_key)
            txs = result.get('tx_responses', [])
            if not txs:
                break
            all_txs.extend(txs)
            page += 1
            pagination = result.get('pagination', {})
            pagination_key = pagination.get('next_key')
            if not pagination_key:
                break
            print(f"    Fetched {len(all_txs)} transactions (page {page})...")
        return all_txs


def ensure_cryptoorg_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cryptoorg_wallets (
            id SERIAL PRIMARY KEY,
            address VARCHAR(100) UNIQUE NOT NULL,
            label VARCHAR(255),
            is_owned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cryptoorg_transactions (
            id SERIAL PRIMARY KEY,
            tx_hash VARCHAR(128) UNIQUE NOT NULL,
            wallet_id INTEGER REFERENCES cryptoorg_wallets(id),
            height BIGINT,
            block_timestamp TIMESTAMP,
            tx_type VARCHAR(50),
            sender VARCHAR(100),
            recipient VARCHAR(100),
            is_outgoing BOOLEAN,
            amount DECIMAL(30, 10),
            denom VARCHAR(50),
            fee DECIMAL(20, 10),
            success BOOLEAN,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cryptoorg_indexing_progress (
            wallet_id INTEGER PRIMARY KEY REFERENCES cryptoorg_wallets(id),
            last_height BIGINT DEFAULT 0,
            total_fetched INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    conn.close()


def get_cryptoorg_wallet_id(address: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM cryptoorg_wallets WHERE address = %s", (address,))
    row = cur.fetchone()

    if row:
        conn.close()
        return row[0]

    cur.execute(
        "INSERT INTO cryptoorg_wallets (address, label, is_owned) VALUES (%s, %s, TRUE) RETURNING id",
        (address, 'Crypto.org Wallet')
    )
    wallet_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return wallet_id


def get_last_cryptoorg_height(wallet_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT last_height FROM cryptoorg_indexing_progress WHERE wallet_id = %s", (wallet_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def update_cryptoorg_progress(wallet_id: int, height: int, total_fetched: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cryptoorg_indexing_progress (wallet_id, last_height, total_fetched, status, updated_at)
        VALUES (%s, %s, %s, 'complete', NOW())
        ON CONFLICT(wallet_id) DO UPDATE SET
            last_height = EXCLUDED.last_height,
            total_fetched = cryptoorg_indexing_progress.total_fetched + EXCLUDED.total_fetched,
            status = 'complete',
            updated_at = NOW()
    """, (wallet_id, height, total_fetched))
    conn.commit()
    conn.close()


def parse_cryptoorg_transaction(tx_resp: Dict, wallet_address: str) -> Dict:
    tx_hash = tx_resp.get('txhash', '')
    height = int(tx_resp.get('height', 0))
    timestamp = tx_resp.get('timestamp', '')

    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        unix_timestamp = int(dt.timestamp())
    except Exception:
        unix_timestamp = 0

    tx = tx_resp.get('tx', {})
    body = tx.get('body', {})
    messages = body.get('messages', [])

    tx_type = 'unknown'
    sender = ''
    recipient = ''
    amount = Decimal(0)
    denom = 'basecro'

    for msg in messages:
        msg_type = msg.get('@type', '')

        if 'MsgSend' in msg_type:
            tx_type = 'transfer'
            sender = msg.get('from_address', '')
            recipient = msg.get('to_address', '')
            amounts = msg.get('amount', [])
            if amounts:
                amount = Decimal(amounts[0].get('amount', '0'))
                denom = amounts[0].get('denom', 'basecro')
        elif 'MsgDelegate' in msg_type:
            tx_type = 'delegate'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')
            amt = msg.get('amount', {})
            amount = Decimal(amt.get('amount', '0'))
            denom = amt.get('denom', 'basecro')
        elif 'MsgUndelegate' in msg_type:
            tx_type = 'undelegate'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')
            amt = msg.get('amount', {})
            amount = Decimal(amt.get('amount', '0'))
            denom = amt.get('denom', 'basecro')
        elif 'MsgWithdrawDelegatorReward' in msg_type:
            tx_type = 'claim_rewards'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')

    is_outgoing = sender.lower() == wallet_address.lower()

    auth_info = tx.get('auth_info', {})
    fee_info = auth_info.get('fee', {})
    fee_amounts = fee_info.get('amount', [])
    fee = Decimal(fee_amounts[0].get('amount', '0')) if fee_amounts else Decimal(0)

    code = tx_resp.get('code', 0)
    success = code == 0

    return {
        'tx_hash': tx_hash,
        'height': height,
        'timestamp': unix_timestamp,
        'tx_type': tx_type,
        'sender': sender,
        'recipient': recipient,
        'is_outgoing': is_outgoing,
        'amount': amount,
        'denom': denom,
        'fee': fee,
        'success': success,
        'raw_json': str(tx_resp)[:10000]
    }


def index_cryptoorg_account(address: str, force: bool = False) -> int:
    indexer = CryptoOrgIndexer()

    # Ensure tables exist
    ensure_cryptoorg_tables()

    wallet_id = get_cryptoorg_wallet_id(address)
    start_height = 0 if force else get_last_cryptoorg_height(wallet_id)

    print(f"{address}: Starting from height {start_height}")

    try:
        balances = indexer.get_account_balance(address)
        for denom, amount in balances.items():
            print(f"  Balance: {amount:.6f} {denom}")
        if not balances:
            print("  Balance: 0 CRO")

        print("  Fetching transactions...")
        txs = indexer.get_all_transactions(address)
        print(f"  Found {len(txs)} transactions")

        if not txs:
            print(f"{address}: No new transactions")
            return 0

        conn = get_connection()
        cur = conn.cursor()
        total_indexed = 0
        max_height = start_height

        for tx_resp in txs:
            parsed = parse_cryptoorg_transaction(tx_resp, address)
            if parsed['height'] <= start_height:
                continue
            max_height = max(max_height, parsed['height'])

            try:
                cur.execute("""
                    INSERT INTO cryptoorg_transactions
                    (tx_hash, wallet_id, height, block_timestamp,
                     tx_type, sender, recipient, is_outgoing,
                     amount, denom, fee, success, raw_json)
                    VALUES (%s, %s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tx_hash) DO NOTHING
                """, (
                    parsed['tx_hash'],
                    wallet_id,
                    parsed['height'],
                    parsed['timestamp'],
                    parsed['tx_type'],
                    parsed['sender'],
                    parsed['recipient'],
                    parsed['is_outgoing'],
                    str(parsed['amount']),
                    parsed['denom'],
                    str(parsed['fee']),
                    parsed['success'],
                    parsed['raw_json']
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting tx: {e}")

        conn.commit()
        conn.close()

        if max_height > start_height:
            update_cryptoorg_progress(wallet_id, max_height, total_indexed)

        print(f"{address}: Complete! {total_indexed} transactions indexed")
        return total_indexed

    except Exception as e:
        print(f"{address}: Error - {e}")
        raise


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        address = sys.argv[1]
        force = '--force' in sys.argv
        try:
            count = index_cryptoorg_account(address, force=force)
            print(f"\nIndexed {count} transactions")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python cryptoorg_indexer.py <cro1...address> [--force]")
