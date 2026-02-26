#!/usr/bin/env python3
"""Carefully categorize transactions step by step.

Rules documented in: docs/INDEXER_RULES.md
"""
import sqlite3

DB_PATH = "/home/deploy/neartax/neartax.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print("=== STEP 1: Delete validator pool transactions (if restored) ===")
pool_wallets = [
    "zavodil.poolv1.near", "aurora.pool.near", "meta-pool.near",
    "vitalpoint.pool.near", "epic.poolv1.near", "openshards.poolv1.near",
    "bisontrails.poolv1.near", "lux.poolv1.near", "figment.poolv1.near"
]
c.execute("""
    SELECT id FROM wallets WHERE account_id IN ({})
""".format(','.join('?' for _ in pool_wallets)), pool_wallets)
pool_ids = [r[0] for r in c.fetchall()]

if pool_ids:
    pool_ids_str = ','.join(str(x) for x in pool_ids)
    c.execute(f"DELETE FROM transactions WHERE wallet_id IN ({pool_ids_str})")
    print(f"Deleted {c.rowcount} validator pool transactions")
    c.execute(f"UPDATE wallets SET is_owned = 0, sync_status = 'skip' WHERE id IN ({pool_ids_str})")
    conn.commit()

print("\n=== STEP 2: Mark DELETE_ACCOUNT beneficiary transfers ===")
# When an account is deleted, the beneficiary receives a TRANSFER from "system"
# These share the same tx_hash as the DELETE_ACCOUNT action
# Find tx_hashes that have DELETE_ACCOUNT actions
c.execute("""
    UPDATE transactions
    SET tax_category = 'delete_account_received', 
        category_notes = 'Received from deleted account via system'
    WHERE action_type = 'TRANSFER'
    AND counterparty = 'system'
    AND direction = 'in'
    AND tx_hash IN (
        SELECT DISTINCT tx_hash FROM transactions WHERE action_type = 'DELETE_ACCOUNT'
    )
    AND tax_category IS NULL
""")
delete_beneficiary_count = c.rowcount
print(f"Marked {delete_beneficiary_count} DELETE_ACCOUNT beneficiary transfers")

# Also mark these as internal if from an owned wallet's deletion
c.execute("""
    UPDATE transactions t1
    SET tax_category = 'internal',
        category_notes = 'Received from own deleted account'
    WHERE t1.tax_category = 'delete_account_received'
    AND EXISTS (
        SELECT 1 FROM transactions t2 
        JOIN wallets w ON t2.wallet_id = w.id
        WHERE t2.tx_hash = t1.tx_hash 
        AND t2.action_type = 'DELETE_ACCOUNT'
        AND w.is_owned = 1
    )
""")
print(f"  -> {c.rowcount} reclassified as internal (from owned accounts)")

print("\n=== STEP 3: Mark internal transfers (between own wallets) ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Transfer from own wallet'
    WHERE direction = 'in'
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND (tax_category IS NULL OR tax_category NOT IN ('internal', 'unstake_return', 'staking_income'))
""")
print(f"Marked {c.rowcount} inflows as internal")

c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Transfer to own wallet'
    WHERE direction = 'out'
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND (tax_category IS NULL OR tax_category NOT IN ('internal', 'staking_deposit'))
""")
print(f"Marked {c.rowcount} outflows as internal")

print("\n=== STEP 4: Mark NEAR Intents (implicit account) transfers ===")
c.execute("""
    UPDATE transactions 
    SET tax_category = 'internal', category_notes = 'NEAR Intents/implicit account'
    WHERE LENGTH(counterparty) = 64
    AND counterparty GLOB '[0-9a-f]*'
    AND (tax_category IS NULL OR tax_category NOT IN ('internal', 'unstake_return', 'staking_income'))
""")
print(f"Marked {c.rowcount} implicit account transactions as internal")

print("\n=== STEP 5: Mark init method deposits as internal (account creation) ===")
# When you create a sub-account with init, you're just moving funds internally
c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Account creation deposit'
    WHERE method_name = 'init'
    AND direction = 'out'
    AND CAST(amount AS REAL) > 0
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} init deposits as internal (to owned accounts)")

# The receiving account's side
c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Account creation received'
    WHERE method_name = 'init'
    AND direction = 'in'
    AND CAST(amount AS REAL) > 0
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} init receipts as internal (from owned accounts)")

print("\n=== STEP 6: Mark leave method refunds ===")
# When you call leave() on a DAO, you get your funds back as a TRANSFER
c.execute("""
    UPDATE transactions
    SET tax_category = 'dao_withdrawal', category_notes = 'DAO membership withdrawal (leave)'
    WHERE action_type = 'TRANSFER'
    AND direction = 'in'
    AND counterparty LIKE '%.cdao.near'
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} DAO leave refunds")

print("\n=== STEP 7: Mark wrap.near deposits ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'defi_deposit', category_notes = 'NEAR wrapped to wNEAR'
    WHERE counterparty = 'wrap.near' AND direction = 'out'
    AND (method_name = 'near_deposit' OR method_name IS NULL)
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} wrap.near deposits as defi_deposit")

print("\n=== STEP 8: Mark meta-pool staking deposits ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'staking_deposit', category_notes = 'Meta Pool liquid staking'
    WHERE counterparty = 'meta-pool.near' AND direction = 'out'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} meta-pool deposits as staking_deposit")

print("\n=== STEP 9: Mark validator staking deposits ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'staking_deposit', category_notes = 'Validator staking deposit'
    WHERE counterparty LIKE '%.pool%' AND direction = 'out'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} validator deposits as staking_deposit")

print("\n=== STEP 10: Mark staking withdrawals (from pools) ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'unstake_return', category_notes = 'Staking withdrawal'
    WHERE counterparty LIKE '%.pool%' AND direction = 'in'
    AND action_type = 'TRANSFER'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} staking withdrawals")

print("\n=== STEP 11: Mark Ref Finance swaps ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'swap', category_notes = 'Ref Finance swap'
    WHERE counterparty LIKE '%ref%finance%'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} Ref Finance transactions")

print("\n=== STEP 12: Mark Burrow lending ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'defi_deposit', category_notes = 'Burrow lending deposit'
    WHERE counterparty LIKE '%burrow%' AND direction = 'out'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} Burrow deposits")

c.execute("""
    UPDATE transactions
    SET tax_category = 'defi_withdrawal', category_notes = 'Burrow lending withdrawal'
    WHERE counterparty LIKE '%burrow%' AND direction = 'in'
    AND CAST(amount AS REAL) > 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} Burrow withdrawals")

print("\n=== STEP 13: Mark DeFi operations (0 NEAR amount) as non-taxable ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'non_taxable', category_notes = 'Zero-value DeFi operation'
    WHERE direction = 'out'
    AND (counterparty LIKE '%burrow%' OR counterparty LIKE '%ref%' 
         OR counterparty = 'wrap.near' OR counterparty = 'meta-pool.near')
    AND CAST(amount AS REAL) = 0
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} zero-amount DeFi ops as non_taxable")

print("\n=== STEP 14: Mark system refunds (gas refunds) ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'fee_refund', category_notes = 'Gas refund from system'
    WHERE counterparty = 'system'
    AND direction = 'in'
    AND action_type = 'TRANSFER'
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} system refunds")

print("\n=== STEP 15: Mark key operations as non-taxable ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'non_taxable', category_notes = 'Key management operation'
    WHERE action_type IN ('ADD_KEY', 'DELETE_KEY')
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} key operations as non_taxable")

print("\n=== STEP 16: Mark contract deployments as non-taxable ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'non_taxable', category_notes = 'Contract deployment'
    WHERE action_type = 'DEPLOY_CONTRACT'
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} contract deployments as non_taxable")

print("\n=== STEP 17: Mark CREATE_ACCOUNT as internal (if to owned) ===")
c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Created sub-account'
    WHERE action_type = 'CREATE_ACCOUNT'
    AND direction = 'out'
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} CREATE_ACCOUNT (to owned) as internal")

c.execute("""
    UPDATE transactions
    SET tax_category = 'internal', category_notes = 'Received at account creation'
    WHERE action_type = 'CREATE_ACCOUNT'
    AND direction = 'in'
    AND counterparty IN (SELECT account_id FROM wallets WHERE is_owned = 1)
    AND tax_category IS NULL
""")
print(f"Marked {c.rowcount} CREATE_ACCOUNT received as internal")

conn.commit()

# Final summary
print("\n" + "="*60)
print("=== FINAL CATEGORY SUMMARY ===")
c.execute("""
    SELECT 
        COALESCE(tax_category, 'UNCATEGORIZED') as cat,
        direction,
        SUM(CAST(amount AS REAL)/1e24) as total_near,
        COUNT(*) as cnt
    FROM transactions
    GROUP BY tax_category, direction
    ORDER BY cnt DESC
""")
for row in c.fetchall():
    print(f"  {row[0]:<25} {row[1]:<5} = {row[2]:>12,.2f} NEAR ({row[3]:>6} txs)")

# Uncategorized breakdown
print("\n=== UNCATEGORIZED TRANSACTIONS (sample) ===")
c.execute("""
    SELECT action_type, method_name, counterparty, direction, 
           CAST(amount AS REAL)/1e24 as near_amt, COUNT(*) as cnt
    FROM transactions 
    WHERE tax_category IS NULL
    GROUP BY action_type, method_name, counterparty, direction
    ORDER BY cnt DESC
    LIMIT 20
""")
for row in c.fetchall():
    print(f"  {row[0]:<15} {(row[1] or '-'):<20} {row[2]:<30} {row[3]:<4} {row[4]:>10.2f} NEAR x{row[5]}")

conn.close()
print("\n✅ Categorization complete!")
