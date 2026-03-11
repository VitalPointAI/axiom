# Axiom

Intelligent crypto tax reporting and portfolio analytics platform.

## Features

- **Multi-Chain Portfolio Tracking** - NEAR, Ethereum, and EVM-compatible chains
- **Automated Transaction Indexing** - Historical transaction sync via NearBlocks and Etherscan APIs
- **Tax Report Generation** - Canadian T1135, Schedule 3, capital gains/losses
- **DeFi Support** - Burrow, Ref Finance, Meta Pool staking
- **Fungible Token Tracking** - Automatic FT transaction detection and pricing
- **Staking Rewards** - Epoch-level reward tracking with validator breakdowns
- **Koinly Export** - Compatible CSV exports for tax software

## Tech Stack

- **Frontend:** Next.js 16, React 18, Tailwind CSS
- **Backend:** PostgreSQL, Python indexers
- **Auth:** @vitalpoint/near-phantom-auth (passkeys + NEAR MPC)
- **APIs:** NearBlocks, Etherscan, CoinGecko (historical prices)

## Development

```bash
# Install dependencies
cd web && npm install

# Run development server
npm run dev

# Build for production
npm run build
```

## Database

PostgreSQL with async wrapper for SQLite API compatibility.

```bash
# Connect to database
psql -h localhost -U neartax -d neartax
```

## Deployment

- **Server:** 157.90.122.69 (Hetzner)
- **Process:** PM2 (axiom)
- **Port:** 3003

## License

Private - VitalPointAI
