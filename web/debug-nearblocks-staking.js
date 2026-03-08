const NEARBLOCKS_API = 'https://api.nearblocks.io/v1';
const API_KEY = '0F1F69733B684BD48753570B3B9C4B27';

async function getBalance(account) {
  try {
    const resp = await fetch(`${NEARBLOCKS_API}/account/${account}`, {
      headers: { Authorization: `Bearer ${API_KEY}` }
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    console.log(`\n${account}:`);
    console.log("  raw:", JSON.stringify(data.account?.[0] || {}));
    const acct = data.account?.[0] || {};
    return {
      account,
      liquid: parseFloat(acct.amount || '0') / 1e24,
      staked: parseFloat(acct.staked || '0') / 1e24
    };
  } catch (e) {
    console.log(`Error for ${account}:`, e.message);
    return null;
  }
}

async function main() {
  // Check a few key wallets
  const wallets = ['vitalpointai.near', 'vpointai.cdao.near', 'did.near'];
  
  let totalLiquid = 0;
  let totalStaked = 0;
  
  for (const account of wallets) {
    const result = await getBalance(account);
    if (result) {
      totalLiquid += result.liquid;
      totalStaked += result.staked;
      console.log(`  Parsed: liquid=${result.liquid.toFixed(2)}, staked=${result.staked.toFixed(2)}`);
    }
  }
  
  console.log("\nTotals for sampled wallets:");
  console.log("  Liquid:", totalLiquid.toFixed(2));
  console.log("  Staked:", totalStaked.toFixed(2));
}

main();
