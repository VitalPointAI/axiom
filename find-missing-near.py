#!/usr/bin/env python3
"""Find exactly where the missing NEAR is in CDAO wallets."""
import sqlite3
import requests
import json

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

# Use NearBlocks to get complete transaction history
def get_nearblocks_txns(account):
    """Get all transactions from NearBlocks API."""
    all_txns = []
    cursor = None
    for _ in range(20):  # Max 20 pages
        url = f"https://api.nearblocks.io/v1/account/{account}/txns?per_page=100"
        if cursor:
            url += f"&cursor={cursor}"
        resp = requests.get(url, timeout=15)
        data = resp.json()
        txns = data.get("txns", [])
        if not txns:
            break
        all_txns.extend(txns)
        cursor = data.get("cursor")
        if not cursor:
            break
    return all_txns

for wallet in ["vpacademy.cdao.near"]:  # Start with one
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]
    
    print(f"\n{'='*70}")
    print(f"DEEP ANALYSIS: {wallet}")
    print(f"{'='*70}")
    
    # Get NearBlocks data
    print("\nFetching from NearBlocks...")
    nb_txns = get_nearblocks_txns(wallet)
    print(f"NearBlocks: {len(nb_txns)} receipts")
    
    # Calculate NearBlocks totals
    nb_in = 0
    nb_out = 0
    nb_fees = 0
    
    for tx in nb_txns:
        receiver = tx.get("receiver_account_id", "")
        predecessor = tx.get("predecessor_account_id", "")
        actions = tx.get("actions", []) or []
        
        for a in actions:
            if not isinstance(a, dict):
                continue
            deposit = (a.get("deposit") or 0) / 1e24
            fee = (a.get("fee") or 0) / 1e24
            
            # This wallet is the receiver
            if receiver == wallet and deposit > 0:
                # Exclude self-transfers
                if predecessor != wallet:
                    nb_in += deposit
            
            # This wallet is the sender (predecessor)
            if predecessor == wallet:
                nb_fees += fee
    
    # Get our DB totals
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
        FROM transactions
        WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
    """, (wallet_id, wallet))
    db_in = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
        FROM transactions
        WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
    """, (wallet_id, wallet))
    db_out = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COALESCE(SUM(max_fee), 0) FROM (
            SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
            FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
        )
    """, (wallet_id,))
    db_fees = cur.fetchone()[0]
    
    print(f"\n{'Source':<20} {'IN':>12} {'OUT':>12} {'Fees':>12}")
    print("-" * 60)
    print(f"{'NearBlocks':<20} {nb_in:>12.4f} {'-':>12} {nb_fees:>12.6f}")
    print(f"{'Our DB':<20} {db_in:>12.4f} {db_out:>12.4f} {db_fees:>12.6f}")
    print(f"{'Difference':<20} {nb_in - db_in:>+12.4f} {'-':>12} {nb_fees - db_fees:>+12.6f}")
    
    # Find specific missing transactions
    print("\n--- Checking for missing high-value IN transactions ---")
    
    # Get our tx hashes
    cur.execute("SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ?", (wallet_id,))
    our_hashes = set(r[0] for r in cur.fetchall())
    
    for tx in nb_txns:
        tx_hash = tx.get("transaction_hash", "")
        receiver = tx.get("receiver_account_id", "")
        predecessor = tx.get("predecessor_account_id", "")
        
        if receiver != wallet or predecessor == wallet:
            continue
            
        actions = tx.get("actions", []) or []
        for a in actions:
            if not isinstance(a, dict):
                continue
            deposit = (a.get("deposit") or 0) / 1e24
            
            if deposit > 0.5:  # Only show significant
                in_db = "✓" if tx_hash in our_hashes else "✗ MISSING"
                print(f"  {tx_hash[:16]}... {deposit:10.4f} NEAR from {predecessor[:25]:25} {in_db}")
                
                # If missing, check what we have for this tx
                if tx_hash not in our_hashes:
                    print(f"    ^ This transaction is NOT in our database!")

conn.close()
