#!/usr/bin/env python3
"""
Transaction classifier for Canadian tax treatment.

Classification Types:
- income: Taxable as income (staking rewards, airdrops, mining)
- capital_gain: Taxable capital gain (sell crypto for profit)
- capital_loss: Deductible capital loss (sell crypto at loss)
- transfer: Non-taxable (move between own wallets)
- fee: Cost basis adjustment
- swap: Taxable disposition (crypto-to-crypto trade)
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


# Canadian tax treatment rules
TAX_RULES = {
    # NEAR transaction types
    "TRANSFER": "transfer_or_trade",  # Need to check if internal
    "FUNCTION_CALL": "function_call",  # Check method name
    "STAKE": "transfer",  # Staking is not taxable
    "UNSTAKE": "transfer",  # Unstaking is not taxable
    "ADD_KEY": "fee",
    "DELETE_KEY": "fee",
    "CREATE_ACCOUNT": "fee",
    "DEPLOY_CONTRACT": "fee",
    
    # Staking related methods
    "deposit_and_stake": "transfer",
    "unstake": "transfer",
    "withdraw": "transfer",
    "withdraw_all": "transfer",
    
    # Exchange transaction types
    "buy": "acquisition",  # Cost basis establishment
    "sell": "disposition",  # Capital gain/loss
    "send": "transfer_or_trade",
    "receive": "transfer_or_income",
    "swap": "disposition",  # Crypto-to-crypto is taxable
    "staking_reward": "income",
    "interest": "income",
    "reward": "income",
    "airdrop": "income",
    "mining": "income",
    "dividend": "income",
}


def get_owned_wallets():
    """Get all owned wallet addresses."""
    conn = get_connection()
    
    # NEAR wallets
    near_wallets = set()
    rows = conn.execute(
        "SELECT account_id FROM wallets WHERE is_owned = 1"
    ).fetchall()
    for row in rows:
        near_wallets.add(row[0].lower())
    
    # EVM wallets
    evm_wallets = set()
    rows = conn.execute(
        "SELECT address FROM evm_wallets WHERE is_owned = 1"
    ).fetchall()
    for row in rows:
        evm_wallets.add(row[0].lower())
    
    conn.close()
    return near_wallets, evm_wallets


def is_internal_transfer(from_addr, to_addr, owned_wallets):
    """Check if a transfer is between owned wallets."""
    from_owned = from_addr.lower() in owned_wallets
    to_owned = to_addr.lower() in owned_wallets
    return from_owned and to_owned


def classify_near_transaction(tx, owned_wallets):
    """
    Classify a NEAR transaction for tax purposes.
    
    Returns:
    {
        'classification': 'income' | 'capital_gain' | 'capital_loss' | 'transfer' | 'fee' | 'acquisition',
        'taxable': True | False,
        'notes': 'explanation'
    }
    """
    action_type = tx.get('action_type', '').upper()
    method_name = tx.get('method_name', '')
    direction = tx.get('direction', '')
    counterparty = tx.get('counterparty', '')
    amount = float(tx.get('amount', 0) or 0)
    
    # Check for staking-related transactions
    if method_name in ['deposit_and_stake', 'stake']:
        return {
            'classification': 'staking_deposit',
            'taxable': False,
            'notes': 'Staking deposit - not taxable event'
        }
    
    if method_name in ['unstake', 'withdraw', 'withdraw_all']:
        return {
            'classification': 'staking_withdrawal',
            'taxable': False,
            'notes': 'Staking withdrawal - not taxable event'
        }
    
    # Check for transfers
    if action_type == 'TRANSFER':
        if amount == 0:
            return {
                'classification': 'fee',
                'taxable': False,
                'notes': 'Zero-amount transfer (gas only)'
            }
        
        # Check if internal transfer
        if is_internal_transfer(tx.get('predecessor_id', ''), counterparty, owned_wallets):
            return {
                'classification': 'internal_transfer',
                'taxable': False,
                'notes': 'Transfer between owned wallets'
            }
        
        if direction == 'in':
            # Incoming - could be income or transfer from exchange
            return {
                'classification': 'receive',
                'taxable': 'unknown',  # Need manual review
                'notes': 'Incoming transfer - review if income or acquisition'
            }
        else:
            # Outgoing - could be sale, gift, or payment
            return {
                'classification': 'send',
                'taxable': 'unknown',  # Need manual review
                'notes': 'Outgoing transfer - review if disposition or transfer'
            }
    
    # Function calls - usually fees
    if action_type == 'FUNCTION_CALL':
        return {
            'classification': 'contract_interaction',
            'taxable': False,
            'notes': f'Contract call: {method_name}'
        }
    
    # Account operations
    if action_type in ['ADD_KEY', 'DELETE_KEY', 'CREATE_ACCOUNT', 'DEPLOY_CONTRACT']:
        return {
            'classification': 'fee',
            'taxable': False,
            'notes': f'Account operation: {action_type}'
        }
    
    # Default - flag for review
    return {
        'classification': 'unknown',
        'taxable': 'unknown',
        'notes': f'Unknown action type: {action_type}'
    }


def classify_exchange_transaction(tx):
    """
    Classify an exchange transaction for tax purposes.
    """
    tx_type = tx.get('tx_type', '').lower()
    
    if tx_type in ['buy', 'purchase']:
        return {
            'classification': 'acquisition',
            'taxable': False,
            'notes': 'Purchase - establishes cost basis'
        }
    
    if tx_type in ['sell', 'sale']:
        return {
            'classification': 'disposition',
            'taxable': True,
            'notes': 'Sale - capital gain/loss event'
        }
    
    if tx_type in ['swap', 'convert', 'trade']:
        return {
            'classification': 'disposition',
            'taxable': True,
            'notes': 'Crypto swap - taxable disposition'
        }
    
    if tx_type in ['staking_reward', 'interest', 'reward', 'dividend']:
        return {
            'classification': 'income',
            'taxable': True,
            'notes': f'{tx_type} - taxable income at FMV'
        }
    
    if tx_type in ['send', 'withdrawal']:
        return {
            'classification': 'transfer',
            'taxable': False,
            'notes': 'Withdrawal - not taxable if to own wallet'
        }
    
    if tx_type in ['receive', 'deposit']:
        return {
            'classification': 'transfer',
            'taxable': False,
            'notes': 'Deposit - not taxable if from own source'
        }
    
    if tx_type in ['airdrop']:
        return {
            'classification': 'income',
            'taxable': True,
            'notes': 'Airdrop - taxable income at FMV when received'
        }
    
    return {
        'classification': 'unknown',
        'taxable': 'unknown',
        'notes': f'Unknown transaction type: {tx_type}'
    }


def classify_all_transactions():
    """Classify all transactions in the database."""
    near_wallets, evm_wallets = get_owned_wallets()
    all_owned = near_wallets | evm_wallets
    
    conn = get_connection()
    stats = {
        'income': 0,
        'disposition': 0,
        'acquisition': 0,
        'transfer': 0,
        'fee': 0,
        'unknown': 0
    }
    
    # Classify NEAR transactions
    rows = conn.execute("""
        SELECT id, action_type, method_name, direction, counterparty, amount
        FROM transactions
    """).fetchall()
    
    for row in rows:
        tx = {
            'id': row[0],
            'action_type': row[1],
            'method_name': row[2],
            'direction': row[3],
            'counterparty': row[4],
            'amount': row[5]
        }
        result = classify_near_transaction(tx, all_owned)
        classification = result['classification']
        
        # Map to stats categories
        if classification in ['income', 'staking_reward']:
            stats['income'] += 1
        elif classification in ['disposition', 'capital_gain', 'capital_loss']:
            stats['disposition'] += 1
        elif classification == 'acquisition':
            stats['acquisition'] += 1
        elif classification in ['transfer', 'internal_transfer', 'staking_deposit', 'staking_withdrawal']:
            stats['transfer'] += 1
        elif classification in ['fee', 'contract_interaction']:
            stats['fee'] += 1
        else:
            stats['unknown'] += 1
    
    # Classify exchange transactions
    rows = conn.execute("SELECT id, tx_type FROM exchange_transactions").fetchall()
    
    for row in rows:
        tx = {'id': row[0], 'tx_type': row[1]}
        result = classify_exchange_transaction(tx)
        classification = result['classification']
        
        if classification == 'income':
            stats['income'] += 1
        elif classification == 'disposition':
            stats['disposition'] += 1
        elif classification == 'acquisition':
            stats['acquisition'] += 1
        elif classification == 'transfer':
            stats['transfer'] += 1
        else:
            stats['unknown'] += 1
    
    conn.close()
    return stats


if __name__ == "__main__":
    stats = classify_all_transactions()
    print("\nClassification Summary:")
    print("-" * 40)
    for classification, count in stats.items():
        print(f"  {classification:15}: {count:6}")
    total = sum(stats.values())
    print("-" * 40)
    print(f"  {'TOTAL':15}: {total:6}")
