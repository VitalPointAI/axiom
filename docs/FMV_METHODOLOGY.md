# Fair Market Value (FMV) Methodology

## Overview

Axiom uses a **tiered pricing approach** to determine the Fair Market Value (FMV)
of cryptocurrency transactions for Canadian tax reporting purposes.

This methodology balances accuracy with performance. Exact-moment pricing is
used for material dispositions where intraday volatility could meaningfully
affect reported capital gains. Daily closing prices are used for routine
transactions where the tax impact of intraday price variation is negligible.

## Pricing Tiers

### Tier 1: On-Chain / Contract Data (Exact)

**Used for:** Staking rewards, lockup events, DEX swaps with on-chain pricing

When the blockchain transaction itself contains the price or value data
(e.g., staking reward amounts valued at time of receipt by the validator
contract, or lockup vesting events with recorded FMV), Axiom uses that
on-chain data directly.

- **Source:** Blockchain transaction data (staking_events.fmv_cad, lockup_events.fmv_cad)
- **Precision:** Exact at time of transaction
- **API calls:** None
- **Marked as estimated:** No

### Tier 2: Daily Closing Price (Estimated)

**Used for:**
- Staking income and rewards (below $500 CAD)
- Network fees paid
- Transfers between own wallets (no tax event, FMV for records only)
- Small dispositions (below $500 CAD threshold)
- Any transaction where on-chain FMV is not available

The daily closing price is the volume-weighted average price for the
calendar day (UTC) of the transaction. This is fetched in bulk from
CoinGecko's `market_chart/range` API endpoint, which returns daily data
points for periods longer than 90 days.

- **Source:** CoinGecko daily OHLCV data (primary), CryptoCompare (fallback)
- **Precision:** Daily (typically close price at 00:00 UTC)
- **API calls:** 1 per token per year of history (bulk fetched)
- **Marked as estimated:** Yes
- **Rationale:** CRA accepts reasonable valuation methods for routine
  transactions. Daily closing prices from reputable exchanges are a widely
  accepted standard. The intraday price difference for sub-$500 transactions
  has minimal tax impact (typically < $5 CAD variance).

### Tier 3: Minute-Level Price (High Precision)

**Used for:**
- Dispositions (sells, swaps) where estimated value exceeds **$500 CAD**
- Capital gain/loss events where precise FMV materially affects reported gains

When a Tier 2 daily price estimate indicates the transaction value exceeds
$500 CAD, Axiom automatically upgrades to minute-level pricing. This uses
CoinGecko's `market_chart/range` API with a 2-hour window centered on the
transaction timestamp, selecting the closest available data point.

- **Source:** CoinGecko intraday market data (5-minute granularity)
- **Precision:** Within 5-15 minutes of actual transaction time
- **API calls:** 1 per transaction requiring precision
- **Marked as estimated:** Yes, if closest data point is > 15 minutes away
- **Threshold:** $500 CAD (configurable via `DISPOSITION_PRECISION_THRESHOLD_CAD`)

## CAD Conversion

All FMV calculations use the Bank of Canada daily noon exchange rate
(USD/CAD) published via the Valet API. This is the rate accepted by CRA
for foreign currency conversion.

- **Source:** Bank of Canada Valet API (FXUSDCAD series)
- **Fallback:** CryptoCompare USDT/CAD rate
- **Weekend/Holiday handling:** Uses the most recent business day rate
  (up to 5 business days lookback)
- **Final fallback:** Hardcoded approximate rate of 1.36 CAD/USD

## Price Sources

### Primary: CoinGecko

- Free tier: 30 calls/minute, no API key required
- Pro tier: Higher limits with API key
- Data: Aggregated from 900+ exchanges
- Coverage: 14,000+ cryptocurrencies

### Secondary: CryptoCompare

- Used as fallback when CoinGecko is unavailable
- Used for outlier detection (prices from two sources compared)

### Outlier Detection

When prices are available from both CoinGecko and CryptoCompare, Axiom
compares them. If the prices differ by more than 50%, CoinGecko is used
as the authoritative source (it aggregates from more exchanges). If
within 50%, the average of both sources is used.

## Caching

All price lookups are cached in PostgreSQL to avoid redundant API calls:

- **`price_cache` table:** Daily prices keyed by (coin_id, date, currency)
- **`price_cache_minute` table:** Minute-level prices keyed by (coin_id, unix_ts, currency)
- **Stablecoins:** USDT, USDC, DAI are hardcoded to $1.00 USD (no API call)

Cached prices are never evicted. Subsequent ACB calculations for the same
user are near-instantaneous since all prices are already cached.

## Performance

Initial calculation for a portfolio with ~33,000 transactions:

| Step | API Calls | Time |
|------|-----------|------|
| Bulk daily prices (3 tokens x 3 years) | ~3 calls | ~10 seconds |
| BoC CAD rates (unique dates) | ~1,095 calls | ~2 minutes |
| Minute-level precision (large dispositions) | ~50-200 calls | ~2-5 minutes |
| **Total first run** | **~1,150-1,300** | **~5-8 minutes** |
| **Subsequent runs (all cached)** | **0** | **< 30 seconds** |

## Audit Trail

Every FMV determination is recorded in the `acb_snapshots` table with:

- `price_usd` / `price_cad`: The FMV used for the calculation
- `price_estimated`: Boolean flag indicating if the price was estimated
  (Tier 2 daily) vs. precise (Tier 1 on-chain or Tier 3 minute-level)
- `needs_review`: Set when the system cannot determine a reliable price

The `audit_log` table records a summary row per token after each ACB
calculation, showing the final pool state (total units, total cost CAD).

## Regulatory Basis

This methodology is consistent with CRA guidance for cryptocurrency
valuation:

- **IT-479R (Archived):** CRA accepts "a reasonable method" for determining
  FMV of property
- **Guide T4037:** Capital gains must be calculated using FMV at time of
  disposition
- **CRA Crypto Guide (2023):** Recommends using "a reputable cryptocurrency
  exchange" for price data

The tiered approach ensures that material transactions (dispositions > $500)
receive precise valuation while routine transactions use a well-established
daily pricing methodology that is both defensible and practical.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DISPOSITION_PRECISION_THRESHOLD_CAD` | 500 | CAD threshold above which minute-level pricing is used |
| `COINGECKO_API_KEY` | (optional) | CoinGecko API key for higher rate limits |
| `CRYPTOCOMPARE_API_KEY` | (optional) | CryptoCompare API key for fallback pricing |
