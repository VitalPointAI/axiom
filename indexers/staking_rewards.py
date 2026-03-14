#!/usr/bin/env python3
"""Staking rewards calculator using NearBlocks + FastNear RPC."""

import requests
import base64
import json
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import FASTNEAR_RPC
from indexers.nearblocks_client import NearBlocksClient


def get_pool_balance(account_id, pool_id):
    """Query validator pool for account's current staked balance."""
    try:
        args = json.dumps({"account_id": account_id})
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
                    "account_id": pool_id,
                    "method_name": "get_account_staked_balance",
                    "args_base64": args_b64
                }
            },
            timeout=10
        )
        
        result = response.json().get("result", {})
        if "result" in result:
            # Decode the result (it's a JSON string in bytes)
            balance_bytes = bytes(result["result"])
            balance_str = balance_bytes.decode().strip('"')
            if balance_str.isdigit():
                return int(balance_str) / 1e24
    except Exception:
        pass  # Silently fail - pool might not exist or account not staked
    
    return 0


def get_staking_summary(account_id):
    """
    Get staking summary using NearBlocks kitwallet endpoint.
    Returns deposits/withdrawals per validator.
    """
    client = NearBlocksClient()
    
    try:
        deposits = client.fetch_staking_deposits(account_id)
    except Exception as e:
        print(f"Error fetching staking data: {e}")
        return []
    
    summary = []
    for item in deposits:
        validator_id = item.get("validator_id")
        deposit = int(item.get("deposit", 0))
        
        # Positive deposit = currently staked
        # Negative deposit = fully withdrawn (net = deposited - withdrawn)
        if deposit > 0:
            # Get current balance from pool
            current = get_pool_balance(account_id, validator_id)
            net_deposit_near = deposit / 1e24
            rewards = current - net_deposit_near if current > 0 else 0
            status = "active"
        else:
            # Already withdrawn
            current = 0
            net_deposit_near = deposit / 1e24  # Negative
            rewards = 0  # Can't calculate for closed positions
            status = "withdrawn"
        
        summary.append({
            "validator_id": validator_id,
            "status": status,
            "net_deposit_yocto": deposit,
            "net_deposit_near": net_deposit_near,
            "current_staked": current,
            "estimated_rewards": rewards
        })
    
    return summary


def calculate_rewards(account_id):
    """
    Calculate total staking rewards.
    
    Formula: rewards = current_staked - net_deposits (for active stakes)
    
    Note: For closed positions (fully withdrawn), we can't calculate rewards
    accurately without full transaction history. Mark as "unknown".
    """
    summary = get_staking_summary(account_id)
    
    total_current = 0
    total_rewards = 0
    active_validators = []
    withdrawn_validators = []
    
    for v in summary:
        if v["status"] == "active":
            total_current += v["current_staked"]
            total_rewards += v["estimated_rewards"]
            active_validators.append({
                "validator": v["validator_id"],
                "staked": v["current_staked"],
                "rewards": v["estimated_rewards"]
            })
        else:
            withdrawn_validators.append(v["validator_id"])
    
    return {
        "account_id": account_id,
        "total_currently_staked": total_current,
        "total_estimated_rewards": total_rewards,
        "active_stakes": active_validators,
        "withdrawn_validators": withdrawn_validators,
        "note": "Rewards for withdrawn validators require full tx history analysis"
    }


def print_staking_summary(result):
    """Pretty print staking summary."""
    print(f"\n{'='*60}")
    print(f"STAKING SUMMARY: {result['account_id']}")
    print(f"{'='*60}")
    
    print(f"\nTotal Currently Staked: {result['total_currently_staked']:.4f} NEAR")
    print(f"Total Estimated Rewards: {result['total_estimated_rewards']:.4f} NEAR")
    
    if result['active_stakes']:
        print("\nActive Stakes:")
        for stake in result['active_stakes']:
            print(f"  {stake['validator']}")
            print(f"    Staked:  {stake['staked']:.4f} NEAR")
            print(f"    Rewards: {stake['rewards']:.4f} NEAR")
    
    if result['withdrawn_validators']:
        print("\nWithdrawn Validators (rewards unknown):")
        for v in result['withdrawn_validators']:
            print(f"  - {v}")
    
    print(f"\nNote: {result['note']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    account = sys.argv[1] if len(sys.argv) > 1 else "vitalpointai.near"
    result = calculate_rewards(account)
    print_staking_summary(result)
