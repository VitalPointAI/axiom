#!/usr/bin/env python3
"""
Tax transaction categories following Koinly's taxonomy.
Maps NEAR blockchain activity to tax-relevant categories.
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass


class TaxCategory(Enum):
    """
    Transaction categories for tax purposes.
    Based on Koinly's categorization system.
    """
    # === INCOME (Taxable) ===
    REWARD = "reward"              # Staking rewards, validator rewards
    AIRDROP = "airdrop"            # Free tokens received
    MINING = "mining"              # Mining rewards (not common on NEAR)
    INTEREST = "interest"          # Interest earned (DeFi lending)
    INCOME = "income"              # Other taxable income
    BOUNTY = "bounty"              # Bug bounties, work rewards
    
    # === TRADES (Capital Gains) ===
    BUY = "buy"                    # Purchase with fiat
    SELL = "sell"                  # Sale to fiat
    TRADE = "trade"                # Crypto-to-crypto swap
    
    # === TRANSFERS (Non-taxable, but track cost basis) ===
    TRANSFER_IN = "transfer_in"    # Received from own wallet
    TRANSFER_OUT = "transfer_out"  # Sent to own wallet
    DEPOSIT = "deposit"            # Received from external (unknown if own)
    WITHDRAWAL = "withdrawal"      # Sent to external (unknown if own)
    
    # === STAKING ===
    STAKE = "stake"                # Tokens locked for staking
    UNSTAKE = "unstake"            # Tokens unlocked from staking
    
    # === DEFI ===
    LIQUIDITY_IN = "liquidity_in"  # Add liquidity to pool
    LIQUIDITY_OUT = "liquidity_out"  # Remove liquidity
    LOAN_BORROW = "loan_borrow"    # Borrowing (not taxable)
    LOAN_REPAY = "loan_repay"      # Repaying loan
    COLLATERAL_IN = "collateral_in"    # Depositing collateral
    COLLATERAL_OUT = "collateral_out"  # Withdrawing collateral
    LIQUIDATION = "liquidation"    # Position liquidated
    
    # === EXPENSES (Deductible) ===
    FEE = "fee"                    # Transaction/gas fees
    INTEREST_PAID = "interest_paid"  # Interest on loans
    
    # === OTHER ===
    GIFT_RECEIVED = "gift_received"  # Gift from others
    GIFT_SENT = "gift_sent"        # Gift to others (may have CGT)
    DONATION = "donation"          # Charitable donation
    LOST = "lost"                  # Lost/stolen (capital loss)
    SPAM = "spam"                  # Spam/dust (ignore)
    NFT_MINT = "nft_mint"          # Minting NFT (cost basis)
    NFT_PURCHASE = "nft_purchase"  # Buying NFT
    NFT_SALE = "nft_sale"          # Selling NFT
    CONTRACT_DEPLOY = "contract_deploy"  # Deploying smart contract
    ACCOUNT_CREATE = "account_create"    # Creating NEAR account
    INTERNAL = "internal"          # Internal/non-taxable operations
    UNKNOWN = "unknown"            # Needs manual review


@dataclass
class CategoryResult:
    """Result of transaction categorization."""
    category: TaxCategory
    confidence: float  # 0.0 to 1.0
    notes: str = ""
    needs_review: bool = False


# Known contract patterns for categorization
STAKING_CONTRACTS = [
    ".poolv1.near",
    ".pool.near", 
    "aurora.pool.near",
]

DEX_CONTRACTS = [
    "v2.ref-finance.near",
    "ref-finance.near",
    "jumbo_exchange.near",
]

LENDING_CONTRACTS = [
    "burrow.near",
    "contract.main.burrow.near",
]

BRIDGE_CONTRACTS = [
    "aurora",
    "rainbow-bridge",
    "factory.bridge.near",
]


def categorize_near_transaction(
    action_type: str,
    method_name: Optional[str],
    counterparty: str,
    direction: str,  # "in" or "out"
    amount: int,
    is_own_wallet: bool = False,  # If counterparty is user's own wallet
) -> CategoryResult:
    """
    Categorize a NEAR transaction for tax purposes.
    
    Args:
        action_type: NEAR action type (TRANSFER, FUNCTION_CALL, etc.)
        method_name: Contract method called (for FUNCTION_CALL)
        counterparty: The other party in the transaction
        direction: "in" for received, "out" for sent
        amount: Amount in yoctoNEAR
        is_own_wallet: Whether counterparty is user's own wallet
    
    Returns:
        CategoryResult with category, confidence, and notes
    """
    method = (method_name or "").lower()
    counter = (counterparty or "").lower()
    
    # === STAKING ===
    if any(s in counter for s in STAKING_CONTRACTS):
        if method in ["deposit_and_stake", "stake", "deposit"]:
            return CategoryResult(TaxCategory.STAKE, 0.95, "Staking deposit")
        if method in ["unstake", "unstake_all"]:
            return CategoryResult(TaxCategory.UNSTAKE, 0.95, "Unstaking")
        if method in ["withdraw", "withdraw_all"]:
            return CategoryResult(TaxCategory.UNSTAKE, 0.90, "Staking withdrawal")
        if method == "ping":
            return CategoryResult(TaxCategory.INTERNAL, 0.99, "Validator ping")
        if direction == "in" and amount > 0:
            return CategoryResult(TaxCategory.REWARD, 0.85, "Likely staking reward")
    
    # === DEX / SWAPS ===
    if any(d in counter for d in DEX_CONTRACTS):
        if method in ["swap", "ft_transfer_call"] and direction == "out":
            return CategoryResult(TaxCategory.TRADE, 0.90, "DEX swap (outgoing leg)")
        if direction == "in" and amount > 0:
            return CategoryResult(TaxCategory.TRADE, 0.85, "DEX swap (incoming leg)")
        if method in ["add_liquidity", "add_stable_liquidity"]:
            return CategoryResult(TaxCategory.LIQUIDITY_IN, 0.90, "LP deposit")
        if method in ["remove_liquidity"]:
            return CategoryResult(TaxCategory.LIQUIDITY_OUT, 0.90, "LP withdrawal")
    
    # === LENDING / BURROW ===
    if any(lc in counter for lc in LENDING_CONTRACTS):
        if method in ["supply", "deposit"]:
            return CategoryResult(TaxCategory.COLLATERAL_IN, 0.90, "Lending deposit")
        if method in ["withdraw"]:
            return CategoryResult(TaxCategory.COLLATERAL_OUT, 0.90, "Lending withdrawal")
        if method in ["borrow"]:
            return CategoryResult(TaxCategory.LOAN_BORROW, 0.90, "Borrowing")
        if method in ["repay"]:
            return CategoryResult(TaxCategory.LOAN_REPAY, 0.90, "Loan repayment")
        if method == "claim_reward" or (direction == "in" and "reward" in method):
            return CategoryResult(TaxCategory.INTEREST, 0.85, "Lending interest")
    
    # === FT TRANSFERS ===
    if method in ["ft_transfer", "ft_transfer_call"]:
        if is_own_wallet:
            if direction == "in":
                return CategoryResult(TaxCategory.TRANSFER_IN, 0.90, "FT transfer between own wallets")
            return CategoryResult(TaxCategory.TRANSFER_OUT, 0.90, "FT transfer between own wallets")
        if direction == "in":
            return CategoryResult(TaxCategory.DEPOSIT, 0.70, "FT received - review if payment/gift/etc", needs_review=True)
        return CategoryResult(TaxCategory.WITHDRAWAL, 0.70, "FT sent - review if payment/gift/etc", needs_review=True)
    
    # === NFT ===
    if method in ["nft_mint", "nft_mint_batch"]:
        return CategoryResult(TaxCategory.NFT_MINT, 0.95, "NFT minted")
    if method in ["nft_transfer", "nft_transfer_call"]:
        if direction == "out":
            return CategoryResult(TaxCategory.NFT_SALE, 0.60, "NFT transferred out - review if sale/gift", needs_review=True)
        return CategoryResult(TaxCategory.NFT_PURCHASE, 0.60, "NFT received - review if purchase/gift", needs_review=True)
    
    # === AIRDROPS ===
    if method in ["claim", "claim_airdrop", "claim_tokens"]:
        return CategoryResult(TaxCategory.AIRDROP, 0.85, "Claimed tokens - likely airdrop")
    
    # === BASIC TRANSFERS ===
    if action_type == "TRANSFER":
        if is_own_wallet:
            if direction == "in":
                return CategoryResult(TaxCategory.TRANSFER_IN, 0.95, "NEAR transfer from own wallet")
            return CategoryResult(TaxCategory.TRANSFER_OUT, 0.95, "NEAR transfer to own wallet")
        if direction == "in":
            return CategoryResult(TaxCategory.DEPOSIT, 0.70, "NEAR received - review source", needs_review=True)
        return CategoryResult(TaxCategory.WITHDRAWAL, 0.70, "NEAR sent - review purpose", needs_review=True)
    
    # === ACCOUNT OPERATIONS ===
    if action_type == "CREATE_ACCOUNT":
        return CategoryResult(TaxCategory.ACCOUNT_CREATE, 0.95, "Created NEAR account")
    if action_type == "DEPLOY_CONTRACT":
        return CategoryResult(TaxCategory.CONTRACT_DEPLOY, 0.95, "Contract deployment")
    if action_type in ["ADD_KEY", "DELETE_KEY"]:
        return CategoryResult(TaxCategory.INTERNAL, 0.99, "Key management")
    if action_type == "DELETE_ACCOUNT":
        return CategoryResult(TaxCategory.INTERNAL, 0.90, "Account deletion")
    
    # === FUNCTION CALLS - Generic ===
    if action_type == "FUNCTION_CALL":
        # Check for reward-related methods
        if "reward" in method or "claim" in method:
            return CategoryResult(TaxCategory.REWARD, 0.70, f"Possible reward: {method}", needs_review=True)
        # Storage operations
        if method in ["storage_deposit", "storage_withdraw"]:
            return CategoryResult(TaxCategory.FEE, 0.90, "Storage deposit/fee")
        # Default function call
        return CategoryResult(TaxCategory.UNKNOWN, 0.50, f"Function call: {method}", needs_review=True)
    
    # === FALLBACK ===
    return CategoryResult(TaxCategory.UNKNOWN, 0.30, f"Unrecognized: {action_type}/{method}", needs_review=True)


def get_tax_treatment(category: TaxCategory) -> dict:
    """Get tax treatment info for a category."""
    treatments = {
        # Income - taxable as ordinary income
        TaxCategory.REWARD: {"taxable": True, "type": "income", "description": "Taxed as ordinary income at FMV when received"},
        TaxCategory.AIRDROP: {"taxable": True, "type": "income", "description": "Taxed as ordinary income at FMV when received"},
        TaxCategory.INTEREST: {"taxable": True, "type": "income", "description": "Taxed as interest income"},
        TaxCategory.INCOME: {"taxable": True, "type": "income", "description": "Taxed as ordinary income"},
        TaxCategory.BOUNTY: {"taxable": True, "type": "income", "description": "Taxed as ordinary income"},
        TaxCategory.MINING: {"taxable": True, "type": "income", "description": "Taxed as ordinary income"},
        
        # Capital gains
        TaxCategory.TRADE: {"taxable": True, "type": "capital_gain", "description": "May trigger capital gain/loss"},
        TaxCategory.SELL: {"taxable": True, "type": "capital_gain", "description": "Capital gain/loss on disposal"},
        TaxCategory.NFT_SALE: {"taxable": True, "type": "capital_gain", "description": "Capital gain/loss on NFT sale"},
        
        # Cost basis establishment
        TaxCategory.BUY: {"taxable": False, "type": "cost_basis", "description": "Establishes cost basis"},
        TaxCategory.NFT_PURCHASE: {"taxable": False, "type": "cost_basis", "description": "Establishes cost basis for NFT"},
        TaxCategory.NFT_MINT: {"taxable": False, "type": "cost_basis", "description": "Cost basis = minting cost"},
        
        # Non-taxable transfers
        TaxCategory.TRANSFER_IN: {"taxable": False, "type": "transfer", "description": "Internal transfer - not taxable"},
        TaxCategory.TRANSFER_OUT: {"taxable": False, "type": "transfer", "description": "Internal transfer - not taxable"},
        TaxCategory.DEPOSIT: {"taxable": False, "type": "transfer", "description": "Received - may need review"},
        TaxCategory.WITHDRAWAL: {"taxable": False, "type": "transfer", "description": "Sent - may need review"},
        
        # Staking
        TaxCategory.STAKE: {"taxable": False, "type": "staking", "description": "Staking deposit - not taxable"},
        TaxCategory.UNSTAKE: {"taxable": False, "type": "staking", "description": "Unstaking - not taxable"},
        
        # DeFi
        TaxCategory.LIQUIDITY_IN: {"taxable": False, "type": "defi", "description": "LP deposit - track cost basis"},
        TaxCategory.LIQUIDITY_OUT: {"taxable": True, "type": "capital_gain", "description": "LP withdrawal - may have gains"},
        TaxCategory.LOAN_BORROW: {"taxable": False, "type": "loan", "description": "Borrowing - not taxable"},
        TaxCategory.LOAN_REPAY: {"taxable": False, "type": "loan", "description": "Repayment - not taxable"},
        TaxCategory.COLLATERAL_IN: {"taxable": False, "type": "collateral", "description": "Collateral deposit - not taxable"},
        TaxCategory.COLLATERAL_OUT: {"taxable": False, "type": "collateral", "description": "Collateral withdrawal - not taxable"},
        TaxCategory.LIQUIDATION: {"taxable": True, "type": "capital_gain", "description": "Forced disposal - capital gain/loss"},
        
        # Expenses
        TaxCategory.FEE: {"taxable": False, "type": "expense", "description": "May be deductible or added to cost basis"},
        TaxCategory.INTEREST_PAID: {"taxable": False, "type": "expense", "description": "May be deductible"},
        TaxCategory.DONATION: {"taxable": False, "type": "expense", "description": "May be tax deductible"},
        
        # Other
        TaxCategory.GIFT_RECEIVED: {"taxable": False, "type": "gift", "description": "Gift - inherits donor's cost basis"},
        TaxCategory.GIFT_SENT: {"taxable": True, "type": "capital_gain", "description": "Gift - may trigger capital gain"},
        TaxCategory.LOST: {"taxable": True, "type": "capital_loss", "description": "Capital loss claim"},
        TaxCategory.SPAM: {"taxable": False, "type": "ignore", "description": "Ignore - no tax implications"},
        TaxCategory.INTERNAL: {"taxable": False, "type": "internal", "description": "Internal operation - not taxable"},
        TaxCategory.CONTRACT_DEPLOY: {"taxable": False, "type": "internal", "description": "Contract deployment - not taxable"},
        TaxCategory.ACCOUNT_CREATE: {"taxable": False, "type": "internal", "description": "Account creation - not taxable"},
        TaxCategory.UNKNOWN: {"taxable": None, "type": "unknown", "description": "Needs manual review"},
    }
    return treatments.get(category, {"taxable": None, "type": "unknown", "description": "Unknown"})
