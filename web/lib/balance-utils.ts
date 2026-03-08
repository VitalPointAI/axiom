/**
 * Shared balance calculation utilities
 * ALL balance calculations should use these to ensure consistency
 */

// Deprecated/duplicate token contracts to exclude
export const EXCLUDED_TOKEN_CONTRACTS = [
  'aurora',  // Deprecated - use eth.bridge.near instead (Aurora migration artifact)
];

// Direction normalization - always use lowercase
export function normalizeDirection(direction: string): 'in' | 'out' {
  const d = direction?.toLowerCase().trim();
  return d === 'in' ? 'in' : 'out';
}

// Check if direction means incoming
export function isIncoming(direction: string): boolean {
  const d = direction?.toLowerCase().trim();
  return d === 'in';
}

// SQL snippet for direction-based balance calculation
export const SQL_BALANCE_CALC = `
  SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS NUMERIC) ELSE 0 END) as total_in,
  SUM(CASE WHEN LOWER(direction) = 'out' THEN CAST(amount AS NUMERIC) ELSE 0 END) as total_out
`;

// SQL snippet for net balance (in - out)
export const SQL_NET_BALANCE = `
  SUM(CASE WHEN LOWER(direction) = 'in' THEN CAST(amount AS NUMERIC) ELSE -CAST(amount AS NUMERIC) END) as net_balance
`;

// SQL WHERE clause to exclude deprecated tokens
export const SQL_EXCLUDE_DEPRECATED_TOKENS = `
  AND token_contract NOT IN ('aurora')
`;

// SQL WHERE clause for spam token filtering (pattern-based)
export const SQL_SPAM_FILTER = `
  AND (token_symbol IS NULL OR (
    token_symbol NOT LIKE '%http%' 
    AND token_symbol NOT LIKE '%visit%' 
    AND token_symbol NOT LIKE '%claim%' 
    AND token_symbol NOT LIKE '%.com%' 
    AND token_symbol NOT LIKE '%.org%'
    AND UPPER(token_symbol) NOT IN (SELECT UPPER(token_symbol) FROM spam_tokens)
  ))
`;

// Calculate balance from transaction array
export function calculateBalance(
  transactions: Array<{ direction: string; amount: string | number }>
): number {
  return transactions.reduce((sum, tx) => {
    const amount = typeof tx.amount === 'string' ? parseFloat(tx.amount) : tx.amount;
    return sum + (isIncoming(tx.direction) ? amount : -amount);
  }, 0);
}

// Token decimal handling
export const TOKEN_DECIMALS: Record<string, number> = {
  'NEAR': 24,
  'wNEAR': 24,
  'wrap.near': 24,
  'rNEAR': 24,
  'lst.rhealab.near': 24,
  'xRHEA': 18,
  'xtoken.rhealab.near': 18,
  'ETH': 18,
  'aurora': 18,
  'eth.bridge.near': 18,
  'USDC': 6,
  'USDT': 6,
  'ZEC': 8,
};

export function getTokenDecimals(tokenContract: string, tokenSymbol?: string): number {
  return TOKEN_DECIMALS[tokenContract] || TOKEN_DECIMALS[tokenSymbol || ''] || 18;
}
