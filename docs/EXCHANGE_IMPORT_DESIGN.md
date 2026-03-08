# Exchange Import System - Improved Design

## Current Problems
1. Generic CSV import doesn't handle exchange-specific formats well
2. No guidance on which files to export
3. No verification step before import
4. Missing fiat transaction data
5. Balances don't reconcile with actual account

## Proposed Flow

### Step 1: Select Exchange
- Show supported exchanges with logos
- Each has specific import requirements

### Step 2: Exchange-Specific Instructions
Show export instructions for each exchange:

#### Crypto.com App
- **Required exports:**
  1. Crypto Wallet transactions (Settings → Export)
  2. Fiat Wallet transactions (separate export)
- **Export format:** CSV
- **Time range:** All time recommended

#### Coinbase
- **Required exports:**
  1. Transaction history CSV
- **Export location:** Settings → Reports → Generate Report

#### Coinsquare
- **Required exports:**
  1. Transaction history CSV
- **Notes:** May need to request from support

### Step 3: Upload Files
- Multi-file upload support
- Drag & drop interface
- Show which files are required vs optional

### Step 4: Preview & Verification
- Parse all files
- Show calculated balances per token
- **Let user input actual current balances for verification**
- Highlight discrepancies
- User can adjust before finalizing

### Step 5: Import & Reconciliation
- Import transactions
- Add adjustment transactions for any balance discrepancies
- Show final imported balances

## Database Changes
- Add  table to track multi-file imports
- Add  table or flag for adjustment transactions
- Add  table for user-verified balances

## UI Components Needed
1. ExchangeSelector - pick exchange with instructions
2. MultiFileUpload - upload required files
3. ImportPreview - show parsed data with verification
4. BalanceReconciliation - compare calculated vs actual
