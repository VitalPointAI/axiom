#!/usr/bin/env python3
"""Lockup contract parser for NEAR Foundation grants."""

import logging
import requests
import base64
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import FASTNEAR_RPC
from indexers.nearblocks_client import NearBlocksClient

# Aaron's lockup contract
LOCKUP_ACCOUNT = "db59d3239f2939bb7d8a4a578aceaa8c85ee8e3f.lockup.near"


def get_lockup_state(lockup_account=LOCKUP_ACCOUNT):
    """Query lockup contract account state via RPC."""
    try:
        response = requests.post(
            FASTNEAR_RPC,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "query",
                "params": {
                    "request_type": "view_account",
                    "finality": "final",
                    "account_id": lockup_account
                }
            },
            timeout=10
        )
        result = response.json().get("result", {})
        return {
            "balance": int(result.get("amount", 0)) / 1e24,
            "storage_used": result.get("storage_usage", 0),
            "code_hash": result.get("code_hash", "")
        }
    except Exception as e:
        return {"error": str(e)}


def call_lockup_method(lockup_account, method_name, args="{}"):
    """Call a view method on the lockup contract."""
    try:
        args_b64 = base64.b64encode(args.encode()).decode()
        
        response = requests.post(
            FASTNEAR_RPC,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "query",
                "params": {
                    "request_type": "call_function",
                    "finality": "final",
                    "account_id": lockup_account,
                    "method_name": method_name,
                    "args_base64": args_b64
                }
            },
            timeout=10
        )
        
        result = response.json().get("result", {})
        if "result" in result:
            value_bytes = bytes(result["result"])
            value_str = value_bytes.decode().strip('"')
            # Try to parse as number
            if value_str.isdigit():
                return int(value_str) / 1e24
            return value_str
        
        if "error" in response.json():
            return None
            
    except (requests.RequestException, ConnectionError, TimeoutError, ValueError, KeyError) as e:
        logger.warning("Failed to call lockup method %s on %s: %s", method_name, lockup_account, e)

    return None


def get_lockup_info(lockup_account=LOCKUP_ACCOUNT):
    """Get lockup contract info via contract calls."""
    methods = [
        "get_balance",
        "get_locked_amount",
        "get_owners_balance",
        "get_liquid_owners_balance",
        "get_staking_pool_account_id",
        "get_known_deposited_balance"
    ]
    
    info = {}
    for method in methods:
        result = call_lockup_method(lockup_account, method)
        if result is not None:
            info[method] = result
    
    return info


def get_lockup_summary(lockup_account=LOCKUP_ACCOUNT):
    """
    Get lockup contract summary.
    
    Aaron confirmed: Vesting COMPLETE as of ~2021 (1 year after opening).
    This is historical data for tax records.
    """
    state = get_lockup_state(lockup_account)
    info = get_lockup_info(lockup_account)
    
    # Get transaction count
    client = NearBlocksClient()
    try:
        tx_count = client.get_transaction_count(lockup_account)
    except (requests.RequestException, ConnectionError, TimeoutError, ValueError, KeyError) as e:
        logger.warning("Failed to get transaction count for %s: %s", lockup_account, e)
        tx_count = "unknown"
    
    return {
        "lockup_account": lockup_account,
        "owner": "vitalpointai.near",
        "vesting_status": "COMPLETE (as of ~2021)",
        "account_state": state,
        "contract_info": info,
        "transaction_count": tx_count,
        "note": "Lockup vesting complete. All funds are liquid.",
        "tax_treatment": {
            "summary": "Tokens became taxable income when vesting unlocked (2020-2021)",
            "action_needed": "Determine original grant amount and vesting schedule from NEAR Foundation records",
            "fmv_needed": "NEAR price at each vesting unlock date"
        }
    }


def print_lockup_summary(result):
    """Pretty print lockup summary."""
    print(f"\n{'='*60}")
    print("LOCKUP CONTRACT SUMMARY")
    print(f"{'='*60}")
    
    print(f"\nAccount: {result['lockup_account']}")
    print(f"Owner: {result['owner']}")
    print(f"Vesting Status: {result['vesting_status']}")
    
    state = result['account_state']
    if 'error' not in state:
        print("\nAccount State:")
        print(f"  Balance: {state['balance']:.4f} NEAR")
        print(f"  Storage: {state['storage_used']:,} bytes")
    
    info = result['contract_info']
    if info:
        print("\nContract Info:")
        for key, value in info.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f} NEAR")
            else:
                print(f"  {key}: {value}")
    
    print(f"\nTransaction Count: {result['transaction_count']}")
    
    print("\nTax Treatment:")
    tax = result['tax_treatment']
    print(f"  {tax['summary']}")
    print(f"  Action: {tax['action_needed']}")
    print(f"  FMV: {tax['fmv_needed']}")
    
    print(f"\nNote: {result['note']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    lockup = sys.argv[1] if len(sys.argv) > 1 else LOCKUP_ACCOUNT
    result = get_lockup_summary(lockup)
    print_lockup_summary(result)
