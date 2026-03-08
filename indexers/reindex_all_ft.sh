#!/bin/bash
# Re-index FT transactions for all NEAR wallets
# Uses delays between wallets to avoid rate limiting

# Load API key
export NEARBLOCKS_API_KEY=0F1F69733B684BD48753570B3B9C4B27

WALLET_IDS=(1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64 89 90 91 97 98)

cd /home/deploy/neartax/indexers

echo "Starting FT re-index for ${#WALLET_IDS[@]} wallets at $(date)"
echo "Using API key: ${NEARBLOCKS_API_KEY:0:8}..."
echo "================================================="

for wallet_id in "${WALLET_IDS[@]}"; do
    echo ""
    echo "Processing wallet ID: $wallet_id"
    python3 ft_indexer_pg.py --wallet-id $wallet_id --force 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✓ Wallet $wallet_id complete"
    else
        echo "✗ Wallet $wallet_id failed"
    fi
    
    # Sleep 15 seconds between wallets to avoid rate limiting
    sleep 15
done

echo ""
echo "================================================="
echo "FT re-index complete at $(date)"
