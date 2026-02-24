#!/usr/bin/env python3
"""
Staking rewards calculator for NEAR Protocol.
Calculates rewards by comparing stake amounts over time.

Rewards = Current staked amount - Total deposited + Total withdrawn

For tax purposes, rewards are taxable as income at time of receipt.
"""

import time
import requests
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.init import get_connection
from indexers.price_service import get_hourly_price

NEARBLOCKS_API_KEY = config.NEARBLOCKS_API_KEY
NEARBLOCKS_BASE = "https://api.nearblocks.io/v1"


def get_headers():
    headers = {}
    if NEARBLOCKS_API_KEY:
        headers["Authorization"] = f"Bearer {NEARBLOCKS_API_KEY}"
    return headers


def get_current_staked_balance(account_id: str, validator: str) -> int:
    """Get current staked balance with a validator."""
    # For delegated staking, we can check via RPC
    # But NearBlocks also provides this via kitwallet API
    url = f"{NEARBLOCKS_BASE}/kitwallet/staking-deposits/{account_id}"
    
    try:
        resp = requests.get(url, headers=get_headers(), timeout=30)
        if resp.status_code == 429:
            time.sleep(30)
            resp = requests.get(url, headers=get_headers(), timeout=30)
        
        data = resp.json()
        
        # Find the validator in the deposits
        for deposit in data:
            if deposit.get("validator_id") == validator:
                return int(deposit.get("deposit", 0))
        
        return 0
    except Exception as e:
        print(f"Error getting staked balance for {account_id} at {validator}: {e}")
        return 0


def calculate_rewards_for_position(wallet_id: int, account_id: str, validator: str) -> dict:
    """
    Calculate rewards for a staking position.
    
    Returns dict with:
    - total_deposited: Sum of all stake deposits
    - total_withdrawn: Sum of all unstake/withdraw events
    - current_staked: Current balance with validator
    - estimated_rewards: current_staked - total_deposited + total_withdrawn
    """
    conn = get_connection()
    
    # Get all deposit amounts (use Python for big int math, not SQL)
    cur = conn.execute("""
        SELECT amount
        FROM staking_events
        WHERE wallet_id = ? AND validator = ?
        AND event_type IN ('deposit_and_stake', 'stake', 'stake_all')
    """, (wallet_id, validator))
    total_deposited = sum(int(row[0]) for row in cur.fetchall() if row[0])
    
    # Get all withdrawn amounts
    cur = conn.execute("""
        SELECT amount
        FROM staking_events
        WHERE wallet_id = ? AND validator = ?
        AND event_type IN ('unstake', 'unstake_all', 'withdraw', 'withdraw_all')
    """, (wallet_id, validator))
    total_withdrawn = sum(int(row[0]) for row in cur.fetchall() if row[0])
    
    conn.close()
    
    # Get current staked balance
    current_staked = get_current_staked_balance(account_id, validator)
    
    # Calculate rewards
    # Rewards = Current + Withdrawn - Deposited
    estimated_rewards = current_staked + total_withdrawn - total_deposited
    
    return {
        "total_deposited": total_deposited,
        "total_withdrawn": total_withdrawn,
        "current_staked": current_staked,
        "estimated_rewards": max(0, estimated_rewards),  # Rewards can't be negative
    }


def get_reward_events_from_blocks(account_id: str, validator: str) -> list:
    """
    Try to find reward distribution events in transaction history.
    Some validators emit events when rewards are distributed.
    """
    # This is validator-specific and complex
    # For now, we'll estimate based on balance changes
    return []


def calculate_all_rewards():
    """Calculate rewards for all staking positions."""
    conn = get_connection()
    
    # Get all unique wallet/validator combinations
    cur = conn.execute("""
        SELECT DISTINCT se.wallet_id, w.account_id, se.validator
        FROM staking_events se
        JOIN wallets w ON se.wallet_id = w.id
    """)
    
    positions = cur.fetchall()
    conn.close()
    
    print(f"Calculating rewards for {len(positions)} staking positions...")
    
    results = []
    for wallet_id, account_id, validator in positions:
        print(f"  {account_id} -> {validator}...")
        
        try:
            rewards = calculate_rewards_for_position(wallet_id, account_id, validator)
            
            deposited_near = rewards["total_deposited"] / 1e24
            withdrawn_near = rewards["total_withdrawn"] / 1e24
            current_near = rewards["current_staked"] / 1e24
            rewards_near = rewards["estimated_rewards"] / 1e24
            
            results.append({
                "account": account_id,
                "validator": validator,
                "deposited": deposited_near,
                "withdrawn": withdrawn_near,
                "current": current_near,
                "rewards": rewards_near,
            })
            
            if rewards_near > 0:
                print(f"    Rewards: {rewards_near:,.2f} NEAR")
            
            time.sleep(1)  # Rate limit
            
        except Exception as e:
            print(f"    Error: {e}")
    
    return results


def print_rewards_summary(results: list):
    """Print a summary of all staking rewards."""
    print("\n" + "=" * 80)
    print("STAKING REWARDS SUMMARY")
    print("=" * 80)
    
    total_rewards = 0
    
    for r in sorted(results, key=lambda x: -x["rewards"]):
        if r["rewards"] > 0:
            print(f"\n{r['account']} -> {r['validator']}")
            print(f"  Deposited:  {r['deposited']:>15,.2f} NEAR")
            print(f"  Withdrawn:  {r['withdrawn']:>15,.2f} NEAR")
            print(f"  Current:    {r['current']:>15,.2f} NEAR")
            print(f"  REWARDS:    {r['rewards']:>15,.2f} NEAR")
            total_rewards += r["rewards"]
    
    print("\n" + "-" * 80)
    print(f"TOTAL ESTIMATED REWARDS: {total_rewards:,.2f} NEAR")
    print("-" * 80)
    
    # Get current price for USD estimate
    price = get_hourly_price("NEAR", int(time.time()) * 1_000_000_000)
    if price:
        print(f"Current value @ ${price:.2f}/NEAR: ${total_rewards * price:,.2f} USD")


if __name__ == "__main__":
    results = calculate_all_rewards()
    print_rewards_summary(results)
