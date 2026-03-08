import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]
    
    # Calculate NET per tx_hash (in - out)
    cur.execute("""
        SELECT tx_hash,
               SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) ELSE 0 END)/1e24 as in_near,
               SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) ELSE 0 END)/1e24 as out_near,
               SUM(CAST(fee AS REAL))/1e24 as fees
        FROM transactions
        WHERE wallet_id = ? AND asset = 'NEAR'
        GROUP BY tx_hash
    """, (wallet_id,))
    
    total_net = 0
    total_fees = 0
    for r in cur.fetchall():
        net = r[1] - r[2]  # in - out for this tx
        total_net += net
        total_fees += r[3]
    
    computed = total_net - total_fees
    
    # Get RPC balance
    resp = requests.post("https://rpc.mainnet.near.org", json={
        "jsonrpc": "2.0", "id": "x",
        "method": "query",
        "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
    }, timeout=10)
    rpc_balance = int(resp.json()["result"]["amount"]) / 1e24
    
    diff = computed - rpc_balance
    
    print(f"{wallet}:")
    print(f"  Net (per-tx):  {total_net:.4f} NEAR")
    print(f"  Fees:          {total_fees:.6f} NEAR")
    print(f"  Computed:      {computed:.4f} NEAR")
    print(f"  RPC:           {rpc_balance:.4f} NEAR")
    print(f"  Diff:          {diff:+.4f} NEAR")
    print()

conn.close()
