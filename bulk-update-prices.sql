-- Bulk update cost basis using price_cache
-- First, create a temp table with date-to-price mapping
CREATE TEMP TABLE IF NOT EXISTS daily_prices AS
SELECT 
    SUBSTR(date, 1, 10) as price_date,
    price as usd_price,
    price * 1.38 as cad_price
FROM price_cache 
WHERE coin_id = "NEAR" AND currency = "USD";

CREATE INDEX IF NOT EXISTS idx_dp ON daily_prices(price_date);

-- Update transactions with cost basis
UPDATE transactions 
SET 
    cost_basis_usd = (CAST(amount AS REAL) / 1e24) * (
        SELECT usd_price FROM daily_prices 
        WHERE price_date = DATE(block_timestamp / 1000000000, "unixepoch")
        LIMIT 1
    ),
    cost_basis_cad = (CAST(amount AS REAL) / 1e24) * (
        SELECT cad_price FROM daily_prices 
        WHERE price_date = DATE(block_timestamp / 1000000000, "unixepoch")
        LIMIT 1
    )
WHERE block_timestamp IS NOT NULL
AND amount IS NOT NULL
AND CAST(amount AS REAL) > 1e20
AND (cost_basis_cad IS NULL OR cost_basis_cad = 0);

-- Show result
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN cost_basis_cad > 0 THEN 1 ELSE 0 END) as priced,
    SUM(CASE WHEN cost_basis_cad IS NULL OR cost_basis_cad = 0 THEN 1 ELSE 0 END) as unpriced
FROM transactions
WHERE amount IS NOT NULL AND CAST(amount AS REAL) > 1e20;
