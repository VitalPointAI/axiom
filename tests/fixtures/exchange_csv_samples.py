"""Sample CSV content for exchange parser tests.

Each constant is a multi-line string representing a realistic CSV export
from the named exchange. Used in unit tests — no live data required.
"""

# ---------------------------------------------------------------------------
# Coinbase CSV
# ---------------------------------------------------------------------------
COINBASE_CSV = """Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,Subtotal,Total,Fees,Notes
2023-01-15 10:30:00 UTC,Buy,BTC,0.10000000,CAD,25000.00,2500.00,2525.00,25.00,
2023-02-20 14:15:00 UTC,Sell,ETH,1.50000000,CAD,2000.00,3000.00,2970.00,30.00,
2023-03-10 09:00:00 UTC,Staking Income,ETH,0.00500000,CAD,2100.00,10.50,10.50,0.00,Staking reward
2023-04-05 11:45:00 UTC,Send,BTC,0.05000000,CAD,26000.00,1300.00,1300.00,0.00,Transfer to hardware wallet
2023-05-01 16:00:00 UTC,Receive,NEAR,100.00000000,CAD,5.00,500.00,500.00,0.00,Transfer from NEAR wallet
"""

# ---------------------------------------------------------------------------
# Crypto.com App CSV
# ---------------------------------------------------------------------------
CRYPTO_COM_APP_CSV = """Timestamp (UTC),Transaction Description,Currency,Amount,To Currency,To Amount,Native Currency,Native Amount,Native Amount (in USD),Transaction Kind
2023-01-10 08:00:00,Buy BTC,BTC,0.05,CAD,1250.00,CAD,1250.00,950.00,crypto_purchase
2023-02-14 12:30:00,Sell ETH,ETH,1.0,CAD,1800.00,CAD,1800.00,1350.00,crypto_exchange
2023-03-20 15:45:00,Staking Reward CRO,CRO,50.0,,,CAD,25.00,18.75,staking_reward
"""

# ---------------------------------------------------------------------------
# Crypto.com Exchange CSV
# ---------------------------------------------------------------------------
CRYPTO_COM_EXCHANGE_CSV = """Trade Date,Pair,Side,Price,Executed,Fee,Total
2023-01-05 09:15:00,BTC_USDT,BUY,22000.00,0.1 BTC,22.00,2222.00
2023-02-10 11:00:00,ETH_USDT,SELL,1600.00,2.0 ETH,3.20,3196.80
2023-03-15 14:30:00,SOL_USDT,BUY,25.50,10 SOL,0.51,255.51
"""

# ---------------------------------------------------------------------------
# Wealthsimple Crypto CSV (CAD-only)
# ---------------------------------------------------------------------------
WEALTHSIMPLE_CSV = """Date,Type,Asset,Quantity,Price,Amount,Fee
2023-01-20,buy,BTC,0.05,28000.00,1400.00,14.00
2023-02-25,sell,ETH,0.5,2200.00,1100.00,11.00
2023-03-30,buy,NEAR,200,4.50,900.00,9.00
"""

# ---------------------------------------------------------------------------
# Uphold CSV (uses Destination Currency / Origin Currency columns)
# ---------------------------------------------------------------------------
UPHOLD_CSV = """Date,Destination Currency,Destination Amount,Origin Currency,Origin Amount,Fee Amount,Fee Currency,Type,Destination,Origin,Status
2023-01-12,BTC,0.05,CAD,1300.00,13.00,CAD,purchase,BTC wallet,CAD wallet,completed
2023-02-18,ETH,1.0,CAD,2100.00,21.00,CAD,purchase,ETH wallet,CAD wallet,completed
2023-03-22,CAD,500.00,ETH,0.25,0.00,CAD,sale,CAD wallet,ETH wallet,completed
"""

# ---------------------------------------------------------------------------
# Coinsquare CSV (uses Action column)
# ---------------------------------------------------------------------------
COINSQUARE_CSV = """Date,Action,Asset,Volume,Total,Market Rate
2023-01-08,buy,BTC,0.1,2400.00,24000.00
2023-02-12,sell,ETH,1.5,3000.00,2000.00
2023-03-18,buy,NEAR,500,2500.00,5.00
"""
