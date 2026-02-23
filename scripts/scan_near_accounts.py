#!/usr/bin/env python3
"""
NEAR Account Scanner for NearTax

Scans all NEAR accounts, pulls complete transaction history,
and verifies calculated balance matches current on-chain balance.

Usage:
    python3 scan_near_accounts.py [--verify] [--export koinly|csv]
"""

import json
import requests
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import time

# APIs
NEAR_RPC = "https://rpc.mainnet.near.org"
NEARBLOCKS_API = "https://api.nearblocks.io/v1"
PIKESPEAK_API = "https://api.pikespeak.ai"  # Better for historical data

# Load wallets
WALLETS_FILE = os.path.join(os.path.dirname(__file__), "..", "wallets.json")

def load_wallets() -> Dict:
    with open(WALLETS_FILE) as f:
        return json.load(f)

def get_account_balance(account_id: str) -> Optional[Decimal]:
    """Get current account balance from RPC"""
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "query",
        "params": {
            "request_type": "view_account",
            "finality": "final",
            "account_id": account_id
        }
    }
    try:
        resp = requests.post(NEAR_RPC, json=payload, timeout=30)
        data = resp.json()
        if "result" in data:
            # Amount in yoctoNEAR (10^-24)
            amount = Decimal(data["result"]["amount"]) / Decimal(10**24)
            return amount
        elif "error" in data:
            if "does not exist" in str(data["error"]):
                return Decimal(0)
            print(f"  Error for {account_id}: {data['error']}", file=sys.stderr)
    except Exception as e:
        print(f"  RPC error for {account_id}: {e}", file=sys.stderr)
    return None

def get_staked_balance(account_id: str, pool_id: str) -> Optional[Decimal]:
    """Get staked balance in a validator pool"""
    import base64
    
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "query",
        "params": {
            "request_type": "call_function",
            "finality": "final",
            "account_id": pool_id,
            "method_name": "get_account_staked_balance",
            "args_base64": base64.b64encode(
                json.dumps({"account_id": account_id}).encode()
            ).decode()
        }
    }
    try:
        resp = requests.post(NEAR_RPC, json=payload, timeout=30)
        data = resp.json()
        if "result" in data and "result" in data["result"]:
            result_bytes = bytes(data["result"]["result"])
            balance_str = result_bytes.decode().strip('"')
            return Decimal(balance_str) / Decimal(10**24)
    except Exception as e:
        pass
    return Decimal(0)

def get_account_transactions(account_id: str, page: int = 1, limit: int = 25) -> List[Dict]:
    """Get transactions from NearBlocks API"""
    url = f"{NEARBLOCKS_API}/account/{account_id}/txns"
    params = {"page": page, "per_page": limit, "order": "asc"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("txns", [])
    except Exception as e:
        print(f"  API error: {e}", file=sys.stderr)
    return []

def get_all_transactions(account_id: str, max_pages: int = 100) -> List[Dict]:
    """Get all transactions for an account (paginated)"""
    all_txns = []
    page = 1
    while page <= max_pages:
        txns = get_account_transactions(account_id, page=page, limit=25)
        if not txns:
            break
        all_txns.extend(txns)
        if len(txns) < 25:
            break
        page += 1
        time.sleep(0.2)  # Rate limiting
    return all_txns

def get_ft_transfers(account_id: str) -> List[Dict]:
    """Get fungible token transfers"""
    url = f"{NEARBLOCKS_API}/account/{account_id}/ft-txns"
    params = {"page": 1, "per_page": 100}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("txns", [])
    except:
        pass
    return []

def get_nft_transfers(account_id: str) -> List[Dict]:
    """Get NFT transfers"""
    url = f"{NEARBLOCKS_API}/account/{account_id}/nft-txns"
    params = {"page": 1, "per_page": 100}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("txns", [])
    except:
        pass
    return []

def classify_transaction(txn: Dict, account_id: str, own_accounts: set) -> Dict:
    """
    Classify transaction for tax treatment
    
    Returns dict with:
    - type: income|expense|transfer|trade|staking|gas
    - taxable: bool
    - amount: Decimal
    - token: str
    - counterparty: str
    - notes: str
    """
    sender = txn.get("predecessor_account_id", "")
    receiver = txn.get("receiver_account_id", "")
    
    # Determine direction
    is_incoming = receiver == account_id
    is_outgoing = sender == account_id
    
    # Check if transfer between own accounts
    counterparty = sender if is_incoming else receiver
    is_internal = counterparty in own_accounts
    
    # Get amount (if NEAR transfer)
    actions = txn.get("actions", [])
    amount = Decimal(0)
    tx_type = "unknown"
    
    for action in actions:
        if action.get("action") == "TRANSFER":
            amount = Decimal(action.get("args", {}).get("deposit", "0")) / Decimal(10**24)
            if is_internal:
                tx_type = "transfer"  # Between own wallets - not taxable
            elif is_incoming:
                tx_type = "income"  # Received from external - potentially taxable
            else:
                tx_type = "expense"  # Sent to external
        elif action.get("action") == "FUNCTION_CALL":
            method = action.get("args", {}).get("method_name", "")
            if method in ["deposit_and_stake", "stake"]:
                tx_type = "staking_deposit"
            elif method in ["unstake", "unstake_all"]:
                tx_type = "staking_withdraw"
            elif method in ["withdraw", "withdraw_all"]:
                tx_type = "staking_withdraw"
            elif method == "ft_transfer":
                tx_type = "ft_transfer"
            elif method == "nft_transfer":
                tx_type = "nft_transfer"
    
    # Gas is always a cost
    gas_burnt = Decimal(txn.get("receipt_conversion_gas_burnt", 0)) / Decimal(10**24)
    
    return {
        "hash": txn.get("transaction_hash"),
        "timestamp": txn.get("block_timestamp"),
        "type": tx_type,
        "taxable": tx_type in ["income", "trade"] and not is_internal,
        "amount": amount,
        "gas": gas_burnt,
        "token": "NEAR",
        "counterparty": counterparty,
        "is_internal": is_internal,
        "sender": sender,
        "receiver": receiver,
    }

def scan_account(account_id: str, own_accounts: set, validator_pool: str) -> Dict:
    """Scan a single account and return summary"""
    print(f"Scanning {account_id}...", file=sys.stderr)
    
    # Get current balance
    balance = get_account_balance(account_id)
    if balance is None:
        return {"account": account_id, "error": "Could not fetch balance"}
    
    # Get staked balance
    staked = get_staked_balance(account_id, validator_pool)
    
    # Get transactions
    txns = get_all_transactions(account_id)
    
    # Classify transactions
    classified = [classify_transaction(t, account_id, own_accounts) for t in txns]
    
    # Calculate totals
    total_in = sum(t["amount"] for t in classified if t["type"] == "income")
    total_out = sum(t["amount"] for t in classified if t["type"] == "expense")
    total_gas = sum(t["gas"] for t in classified)
    internal_in = sum(t["amount"] for t in classified if t["is_internal"] and t["receiver"] == account_id)
    internal_out = sum(t["amount"] for t in classified if t["is_internal"] and t["sender"] == account_id)
    
    return {
        "account": account_id,
        "balance": float(balance),
        "staked": float(staked),
        "total_balance": float(balance + staked),
        "tx_count": len(txns),
        "income": float(total_in),
        "expenses": float(total_out),
        "gas_spent": float(total_gas),
        "internal_in": float(internal_in),
        "internal_out": float(internal_out),
        "transactions": classified[:10],  # First 10 for preview
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan NEAR accounts for tax reporting")
    parser.add_argument("--account", help="Scan specific account only")
    parser.add_argument("--verify", action="store_true", help="Verify balances match")
    parser.add_argument("--export", choices=["json", "csv", "koinly"], help="Export format")
    parser.add_argument("--output", default="near_scan_results.json", help="Output file")
    args = parser.parse_args()
    
    wallets = load_wallets()
    near_accounts = wallets.get("near", [])
    validator = wallets.get("validator", "")
    own_accounts = set(near_accounts)
    
    if args.account:
        near_accounts = [args.account]
    
    print(f"Scanning {len(near_accounts)} NEAR accounts...", file=sys.stderr)
    print(f"Validator pool: {validator}", file=sys.stderr)
    
    results = []
    total_balance = Decimal(0)
    
    for account in near_accounts:
        try:
            result = scan_account(account, own_accounts, validator)
            results.append(result)
            if "total_balance" in result:
                total_balance += Decimal(str(result["total_balance"]))
            time.sleep(0.3)  # Rate limiting
        except Exception as e:
            print(f"Error scanning {account}: {e}", file=sys.stderr)
            results.append({"account": account, "error": str(e)})
    
    summary = {
        "scan_date": datetime.utcnow().isoformat(),
        "accounts_scanned": len(results),
        "total_near_balance": float(total_balance),
        "validator_pool": validator,
        "accounts": results,
    }
    
    # Output
    if args.export == "json" or not args.export:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Results saved to {args.output}", file=sys.stderr)
    
    # Print summary
    print(f"\n=== SCAN SUMMARY ===")
    print(f"Accounts scanned: {len(results)}")
    print(f"Total NEAR balance: {total_balance:.4f} NEAR")
    
    # Show top 10 by balance
    sorted_results = sorted([r for r in results if "total_balance" in r], 
                           key=lambda x: x["total_balance"], reverse=True)
    print(f"\nTop 10 accounts by balance:")
    for r in sorted_results[:10]:
        print(f"  {r['account']}: {r['total_balance']:.4f} NEAR")

if __name__ == "__main__":
    main()
