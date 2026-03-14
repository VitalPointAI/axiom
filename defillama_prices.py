#!/usr/bin/env python3
"""
DeFiLlama Historical Price Fetcher

DeFiLlama provides historical prices for many tokens across multiple chains.
API: https://defillama.com/docs/api

Endpoint: GET https://coins.llama.fi/prices/historical/{timestamp}/{coins}
- timestamp: Unix timestamp
- coins: Comma-separated list of {chain}:{address}

NEAR chain identifier: "near"
"""

import sqlite3
import requests
import time
from typing import Optional, Dict, List
import sys

DEFILLAMA_API = "https://coins.llama.fi"

# NEAR token contract to DeFiLlama identifier mapping
NEAR_TOKEN_MAP = {
    # Native NEAR
    "near": "near:native",
    "wrap.near": "near:wrap.near",
    
    # Major tokens
    "meta-pool.near": "near:meta-pool.near",  # stNEAR
    "token.v2.ref-finance.near": "near:token.v2.ref-finance.near",  # REF
    "token.burrow.near": "near:token.burrow.near",  # BRRR
    "aurora": "aurora:native",  # AURORA
    "token.paras.near": "near:token.paras.near",  # PARAS
    "linear-protocol.near": "near:linear-protocol.near",  # LINEAR
    "meta-token.near": "near:meta-token.near",  # META
    "mpdao-token.near": "near:mpdao-token.near",  # mpDAO
    "token.pembrock.near": "near:token.pembrock.near",  # PEM
    "token.skyward.near": "near:token.skyward.near",  # SKYWARD
    "f5cfbc74057c610c8ef151a439252680ac68c6dc.factory.bridge.near": "near:f5cfbc74057c610c8ef151a439252680ac68c6dc.factory.bridge.near",  # OCT
    "token.sweat": "near:token.sweat",  # SWEAT
    
    # Stablecoins
    "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1": "near:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1",  # USDC
    "usdt.tether-token.near": "near:usdt.tether-token.near",  # USDt
    
    # Bridged tokens (use Ethereum prices)
    "6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near": "ethereum:0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near": "ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC.e
    "dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near": "ethereum:0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT.e
    "2260fac5e5542a773aa44fbcfedf7c193bc2c599.factory.bridge.near": "ethereum:0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "514910771af9ca656af840dff83e8264ecf986ca.factory.bridge.near": "ethereum:0x514910771af9ca656af840dff83e8264ecf986ca",  # LINK
    "1f9840a85d5af5bf1d1762f925bdaddc4201f984.factory.bridge.near": "ethereum:0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",  # UNI
}

# Symbol to contract mapping
SYMBOL_CONTRACT_MAP = {
    "NEAR": "near",
    "wNEAR": "wrap.near",
    "STNEAR": "meta-pool.near",
    "REF": "token.v2.ref-finance.near",
    "BRRR": "token.burrow.near",
    "AURORA": "aurora",
    "PARAS": "token.paras.near",
    "LINEAR": "linear-protocol.near",
    "$META": "meta-token.near",
    "mpDAO": "mpdao-token.near",
    "PEM": "token.pembrock.near",
    "SKYWARD": "token.skyward.near",
    "OCT": "f5cfbc74057c610c8ef151a439252680ac68c6dc.factory.bridge.near",
    "SWEAT": "token.sweat",
    "USDC": "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1",
    "USDt": "usdt.tether-token.near",
    "DAI": "6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near",
    "USDC.e": "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near",
    "USDT.e": "dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near",
}


class DefiLlamaPriceFetcher:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
    
    def get_historical_price(self, token_id: str, timestamp: int) -> Optional[float]:
        """
        Get historical price from DeFiLlama.
        
        Args:
            token_id: DeFiLlama token identifier (e.g., "near:wrap.near")
            timestamp: Unix timestamp (seconds)
        
        Returns:
            Price in USD or None
        """
        url = f"{DEFILLAMA_API}/prices/historical/{timestamp}/{token_id}"
        
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                coins = data.get("coins", {})
                if token_id in coins:
                    return coins[token_id].get("price")
        except Exception as e:
            print(f"Error fetching price for {token_id}: {e}")
        
        return None
    
    def get_batch_historical_prices(self, token_ids: List[str], timestamp: int) -> Dict[str, float]:
        """Get prices for multiple tokens at once (max 100 per request)"""
        prices = {}
        
        # DeFiLlama allows up to 100 tokens per request
        for i in range(0, len(token_ids), 100):
            batch = token_ids[i:i+100]
            coins_param = ",".join(batch)
            
            url = f"{DEFILLAMA_API}/prices/historical/{timestamp}/{coins_param}"
            
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    for token_id, info in data.get("coins", {}).items():
                        if info.get("price"):
                            prices[token_id] = info["price"]
            except Exception as e:
                print(f"Error in batch request: {e}")
            
            time.sleep(0.5)  # Rate limiting
        
        return prices
    
    def get_current_prices(self) -> Dict[str, float]:
        """Get current prices for all known NEAR tokens"""
        token_ids = list(NEAR_TOKEN_MAP.values())
        
        url = f"{DEFILLAMA_API}/prices/current/{','.join(token_ids)}"
        
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                prices = {}
                for token_id, info in data.get("coins", {}).items():
                    if info.get("price"):
                        prices[token_id] = info["price"]
                return prices
        except Exception as e:
            print(f"Error fetching current prices: {e}")
        
        return {}
    
    def price_missing_transactions(self):
        """Price FT transactions using DeFiLlama"""
        cur = self.conn.cursor()
        
        # Get transactions needing prices with their contracts
        cur.execute("""
            SELECT id, token_contract, token_symbol, amount, block_timestamp
            FROM ft_transactions
            WHERE (price_usd IS NULL OR price_usd = 0)
            AND token_contract IS NOT NULL
            AND block_timestamp IS NOT NULL
        """)
        
        rows = cur.fetchall()
        print(f"Found {len(rows)} FT transactions needing prices")
        
        # Group by date and token for batch requests
        date_tokens = {}  # {timestamp: set(token_ids)}
        tx_info = {}  # {tx_id: (token_id, timestamp)}
        
        for row in rows:
            tx_id = row["id"]
            contract = row["token_contract"]
            timestamp = row["block_timestamp"]
            
            # Convert to Unix timestamp (seconds)
            ts_seconds = timestamp // 1_000_000_000
            
            # Get DeFiLlama token ID
            llama_id = NEAR_TOKEN_MAP.get(contract)
            if not llama_id:
                # Try to construct NEAR token ID
                llama_id = f"near:{contract}"
            
            if ts_seconds not in date_tokens:
                date_tokens[ts_seconds] = set()
            date_tokens[ts_seconds].add(llama_id)
            tx_info[tx_id] = (llama_id, ts_seconds, contract, row["amount"])
        
        print(f"Fetching prices for {len(date_tokens)} unique timestamps...")
        
        # Fetch prices for each timestamp
        price_cache = {}  # {(llama_id, timestamp): price}
        
        for i, (ts, token_ids) in enumerate(date_tokens.items()):
            prices = self.get_batch_historical_prices(list(token_ids), ts)
            
            for token_id, price in prices.items():
                price_cache[(token_id, ts)] = price
            
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(date_tokens)} timestamps...")
        
        # Update transactions
        updated = 0
        for tx_id, (llama_id, ts, contract, amount_raw) in tx_info.items():
            price = price_cache.get((llama_id, ts))
            if not price:
                continue
            
            # Determine decimals
            decimals = 24
            if contract == "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1":
                decimals = 6
            elif contract and contract.endswith(".factory.bridge.near"):
                decimals = 18
            
            try:
                amount_decimal = float(amount_raw) / (10 ** decimals)
                value_usd = amount_decimal * price
                value_cad = value_usd * 1.35  # Approximate
                
                self.conn.execute("""
                    UPDATE ft_transactions
                    SET price_usd = ?, value_usd = ?, value_cad = ?
                    WHERE id = ?
                """, (price, value_usd, value_cad, tx_id))
                
                updated += 1
            except Exception:
                pass
        
        self.conn.commit()
        print(f"\nSuccessfully updated {updated} transactions via DeFiLlama")
        return updated


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "neartax.db"
    
    print("=" * 60)
    print("DeFiLlama Historical Price Fetcher")
    print(f"Database: {db_path}")
    print("=" * 60)
    
    fetcher = DefiLlamaPriceFetcher(db_path)
    
    # Show current prices
    print("\nFetching current NEAR ecosystem prices from DeFiLlama...")
    current = fetcher.get_current_prices()
    for token_id, price in sorted(current.items()):
        print(f"  {token_id}: ${price:.4f}")
    
    # Price missing transactions
    print("\nPricing missing FT transactions...")
    updated = fetcher.price_missing_transactions()
    
    print("\n" + "=" * 60)
    print(f"Complete! Updated {updated} transactions")
    print("=" * 60)


if __name__ == "__main__":
    main()
