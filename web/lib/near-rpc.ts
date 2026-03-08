// NEAR RPC Configuration
// Using FastNEAR's mainnet endpoint with API key for better rate limits

const FASTNEAR_API_KEY = process.env.FASTNEAR_API_KEY || '';

export const NEAR_RPC = FASTNEAR_API_KEY 
  ? `https://rpc.mainnet.fastnear.com/${FASTNEAR_API_KEY}`
  : 'https://rpc.fastnear.com';

export async function nearRpcCall(method: string, params: unknown[]) {
  const response = await fetch(NEAR_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 'neartax',
      method,
      params,
    }),
  });
  
  if (!response.ok) {
    throw new Error(`RPC error: ${response.status}`);
  }
  
  const data = await response.json();
  if (data.error) {
    throw new Error(data.error.message || JSON.stringify(data.error));
  }
  
  return data.result;
}

export async function viewAccount(accountId: string) {
  return nearRpcCall('query', [{
    request_type: 'view_account',
    finality: 'final',
    account_id: accountId,
  }]);
}
