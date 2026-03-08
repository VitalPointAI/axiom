#!/bin/bash
# Comprehensive security fix for NearTax - add auth to all data endpoints

cd /home/deploy/neartax/web/app/api

# Helper function to add auth check to a file
add_auth() {
  local file=$1
  
  # Skip if already has getAuthenticatedUser
  if grep -q "getAuthenticatedUser" "$file"; then
    echo "SKIP (already has auth): $file"
    return
  fi
  
  echo "FIXING: $file"
  
  # Add import
  sed -i "1i import { getAuthenticatedUser } from '@/lib/auth';" "$file"
  
  # Add auth check after export async function GET
  sed -i '/export async function GET/a\
  const auth = await getAuthenticatedUser();\
  if (!auth) {\
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });\
  }' "$file"
}

# Fix critical endpoints
echo "=== Fixing critical data endpoints ==="

# Staking
add_auth "staking/route.ts"
add_auth "staking/multichain/route.ts"

# DeFi
add_auth "defi/route.ts"
add_auth "defi/summary/route.ts"
add_auth "defi/positions/route.ts"

# Reports
add_auth "reports/income/route.ts"
add_auth "reports/inventory/route.ts"
add_auth "reports/schedule3/route.ts"
add_auth "reports/summary/route.ts"
add_auth "reports/export/route.ts"
add_auth "reports/t1135/route.ts"
add_auth "reports/ledger/route.ts"
add_auth "reports/other-gains/route.ts"
add_auth "reports/wallet-balances/route.ts"
add_auth "reports/highest-balance/route.ts"
add_auth "reports/buy-sell/route.ts"
add_auth "reports/gifts-donations/route.ts"
add_auth "reports/expenses/route.ts"
add_auth "reports/holdings/route.ts"
add_auth "reports/transactions/route.ts"

# Portfolio
add_auth "portfolio/history/route.ts"
add_auth "portfolio/route.ts"

# Other
add_auth "acb/route.ts"
add_auth "price-warnings/route.ts"
add_auth "validators/route.ts"
add_auth "tally/route.ts"

echo "=== Done adding auth checks ==="
