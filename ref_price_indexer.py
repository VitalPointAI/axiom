#!/usr/bin/env python3
"""
Ref.Finance Historical Price Indexer

Gets historical token prices from Ref.Finance swap events and pool data.
Designed for NearTax to price FT transactions.

Usage:
    python3 ref_price_indexer.py [db_path]
"""

import sqlite3
import requests
import json
from typing import Optional, Dict, Tuple
import sys

# NEAR RPC endpoint
NEAR_RPC = "https://rpc.mainnet.near.org"

# Ref Finance indexer API
REF_INDEXER = "https://indexer.ref.finance"
REF_API = "https://api.ref.finance"

# Token contract to symbol mapping (for tokens not in API)
TOKEN_CONTRACTS = {
    "token.burrow.near": "BRRR",
    "token.pembrock.near": "PEM",
    "meta-token.near": "$META",
    "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near": "USDC.e",
    "dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near": "USDT.e",
    "6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near": "DAI",
    "mpdao-token.near": "mpDAO",
    "token.skyward.near": "SKYWARD",
    "token.lonkingnearbackto2024.near": "LONK",
    "token.rhealab.near": "RHEA",
    "blackdragon.tkn.near": "BLACKDRAGON",
    "meteor-points.near": "MPTS",
    "usn": "USN",
    "token.0xshitzu.near": "SHITZU",
    "xtoken.rhealab.near": "XRHEA",
    "lst.rhealab.near": "rNEAR",
    "linear-protocol.near": "LINEAR",
    "otoken.rhealab.near": "ORHEA",
    "marmaj.tkn.near": "marmaj",
    "token.paras.near": "PARAS",
    "zec.omft.near": "ZEC",
}

# Stablecoin contracts (price = $1)
STABLECOINS = {
    "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1",  # USDC
    "usdt.tether-token.near",  # USDt
    "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near",  # USDC.e
    "dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near",  # USDT.e
    "6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near",  # DAI
    "usn",  # USN
}

# Wrapped NEAR contract
WNEAR = "wrap.near"


class RefPriceIndexer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Cache for current token prices
        self.current_prices: Dict[str, float] = {}
        self.pool_data: Dict[str, dict] = {}
        
        # Load current prices from Ref API
        self._load_current_prices()
        self._load_pool_data()
    
    def _load_current_prices(self):
        """Load current token prices from Ref Finance indexer"""
        try:
            resp = requests.get(f"{REF_INDEXER}/list-token-price", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for contract, info in data.items():
                    if info.get("price"):
                        try:
                            self.current_prices[contract] = float(info["price"])
                        except (ValueError, TypeError):
                            pass
                print(f"Loaded {len(self.current_prices)} current token prices from Ref")
        except Exception as e:
            print(f"Warning: Could not load current prices: {e}")
    
    def _load_pool_data(self):
        """Load pool data from Ref Finance API"""
        try:
            resp = requests.get(f"{REF_API}/list-pools", timeout=30)
            if resp.status_code == 200:
                pools = resp.json()
                for pool in pools:
                    pool_id = pool.get("id")
                    if pool_id:
                        self.pool_data[pool_id] = pool
                print(f"Loaded {len(self.pool_data)} pools from Ref")
        except Exception as e:
            print(f"Warning: Could not load pool data: {e}")
    
    def get_near_price_at_time(self, timestamp_ns: int) -> Optional[float]:
        """Get NEAR price in USD at a specific timestamp using CryptoCompare"""
        timestamp_s = timestamp_ns // 1_000_000_000
        
        # Use CryptoCompare historical price API
        url = "https://min-api.cryptocompare.com/data/pricehistorical"
        params = {
            "fsym": "NEAR",
            "tsyms": "USD",
            "ts": timestamp_s
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("NEAR", {}).get("USD")
        except Exception as e:
            print(f"Warning: Could not get NEAR price: {e}")
        
        return None
    
    def get_token_price_from_swap(self, tx_hash: str, token_contract: str) -> Optional[Tuple[float, str]]:
        """
        Derive token price from a swap transaction.
        Returns (price_usd, method) or None.
        """
        # Query the transaction to get swap details
        try:
            result = requests.post(
                NEAR_RPC,
                json={
                    "jsonrpc": "2.0",
                    "id": "dontcare",
                    "method": "tx",
                    "params": [tx_hash, "system"]
                },
                timeout=30
            )
            
            if result.status_code != 200:
                return None
            
            tx_data = result.json().get("result", {})
            
            # Parse receipts for swap events
            for receipt in tx_data.get("receipts_outcome", []):
                logs = receipt.get("outcome", {}).get("logs", [])
                for log in logs:
                    if "swap" in log.lower():
                        # Parse swap event (JSON format expected)
                        try:
                            # Ref finance swap logs format:
                            # {"EVENT_JSON":{"standard":"ref_exchange","version":"1.0.0","event":"swap","data":[...]}}
                            if "EVENT_JSON" in log:
                                json.loads(log.replace("EVENT_JSON:", ""))
                                # Extract swap data
                                # ... parsing logic here
                        except Exception:
                            pass
            
        except Exception as e:
            print(f"Warning: Could not parse swap tx {tx_hash}: {e}")
        
        return None
    
    def estimate_price_from_pool(self, token_contract: str, near_price: float) -> Optional[float]:
        """
        Estimate token price based on pool ratio with wNEAR.
        """
        for pool_id, pool in self.pool_data.items():
            tokens = pool.get("token_account_ids", [])
            amounts = pool.get("amounts", [])
            
            if len(tokens) == 2 and len(amounts) == 2:
                if token_contract in tokens and WNEAR in tokens:
                    token_idx = tokens.index(token_contract)
                    near_idx = tokens.index(WNEAR)
                    
                    try:
                        token_amount = float(amounts[token_idx])
                        near_amount = float(amounts[near_idx])
                        
                        if token_amount > 0 and near_amount > 0:
                            # Price = (NEAR_amount / token_amount) * NEAR_price
                            # Need to account for decimals
                            # Most tokens are 18 or 24 decimals, NEAR is 24
                            price = (near_amount / token_amount) * near_price
                            return price
                    except (ValueError, ZeroDivisionError):
                        pass
        
        return None
    
    def price_ft_transactions(self, limit: int = None):
        """
        Price all FT transactions that are missing prices.
        """
        cur = self.conn.cursor()
        
        # Get transactions needing prices
        query = """
            SELECT id, token_contract, token_symbol, amount, block_timestamp, tx_hash
            FROM ft_transactions
            WHERE price_usd IS NULL OR price_usd = 0
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cur.execute(query)
        rows = cur.fetchall()
        
        print(f"Found {len(rows)} transactions needing prices")
        
        priced = 0
        for row in rows:
            tx_id = row["id"]
            contract = row["token_contract"]
            row["token_symbol"]
            amount_raw = row["amount"]
            timestamp = row["block_timestamp"]
            row["tx_hash"]
            
            price_usd = None
            
            # 1. Stablecoins = $1
            if contract in STABLECOINS:
                price_usd = 1.0
            
            # 2. Use current price as approximation (for recent txs)
            elif contract in self.current_prices:
                price_usd = self.current_prices[contract]
            
            # 3. Try to estimate from pool ratio
            elif timestamp:
                near_price = self.get_near_price_at_time(timestamp)
                if near_price:
                    estimated = self.estimate_price_from_pool(contract, near_price)
                    if estimated:
                        price_usd = estimated
            
            if price_usd is not None:
                # Calculate value
                try:
                    # Get decimals (default to 24 for NEAR ecosystem)
                    decimals = 24
                    if contract in ["17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"]:
                        decimals = 6  # USDC
                    elif contract.endswith(".factory.bridge.near"):
                        decimals = 18  # Most bridged tokens
                    
                    amount_decimal = float(amount_raw) / (10 ** decimals)
                    value_usd = amount_decimal * price_usd
                    
                    cur.execute("""
                        UPDATE ft_transactions 
                        SET price_usd = ?, value_usd = ?
                        WHERE id = ?
                    """, (price_usd, value_usd, tx_id))
                    
                    priced += 1
                    if priced % 100 == 0:
                        print(f"Priced {priced} transactions...")
                        self.conn.commit()
                        
                except Exception as e:
                    print(f"Error pricing tx {tx_id}: {e}")
        
        self.conn.commit()
        print(f"Successfully priced {priced} transactions")
        return priced
    
    def get_price_summary(self):
        """Show pricing status summary"""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT token_symbol, 
                   COUNT(*) as total,
                   SUM(CASE WHEN price_usd IS NOT NULL AND price_usd > 0 THEN 1 ELSE 0 END) as priced,
                   SUM(CASE WHEN price_usd IS NULL OR price_usd = 0 THEN 1 ELSE 0 END) as missing
            FROM ft_transactions
            GROUP BY token_symbol
            ORDER BY missing DESC
        """)
        
        print("\nToken Pricing Summary:")
        print("-" * 60)
        print(f"{'Token':<20} {'Total':<10} {'Priced':<10} {'Missing':<10}")
        print("-" * 60)
        
        for row in cur.fetchall():
            print(f"{row[0] or 'Unknown':<20} {row[1]:<10} {row[2]:<10} {row[3]:<10}")


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "neartax.db"
    
    print("Ref.Finance Price Indexer")
    print(f"Database: {db_path}")
    print("=" * 60)
    
    indexer = RefPriceIndexer(db_path)
    
    # Show current status
    indexer.get_price_summary()
    
    # Price transactions
    print("\nPricing transactions...")
    indexer.price_ft_transactions()
    
    # Show updated status
    indexer.get_price_summary()


if __name__ == "__main__":
    main()
