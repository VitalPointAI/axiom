"""Seeds classification_rules table from hardcoded patterns.

Converts the rule-of-thumb logic from tax/categories.py into database records
so the classifier engine (Plan 04) can load rules dynamically without code changes.

Run once during migration, or idempotently via seed_classification_rules() at
any time — rules are upserted via ON CONFLICT (name) DO UPDATE using the
uq_cr_name unique constraint created by migration 003.

Priority ordering (checked first = higher number):
  - 100: Staking rules (high confidence, specific contract patterns)
  -  90: DEX / swap rules
  -  80: Lending / collateral rules
  -  70: LP / liquidity rules
  -  60: NFT operations
  -  50: Basic NEAR/EVM transfers and FT ops
  -  40: Exchange-reported tx types (buy/sell/swap/reward/etc.)
  -  10: Fallback / low-confidence patterns
"""

import json

from engine.evm_decoder import EVMDecoder


# ---------------------------------------------------------------------------
# NEAR contract lists (mirrors tax/categories.py)
# ---------------------------------------------------------------------------
STAKING_CONTRACTS = [".poolv1.near", ".pool.near", "aurora.pool.near"]
DEX_CONTRACTS = ["v2.ref-finance.near", "ref-finance.near", "jumbo_exchange.near"]
LENDING_CONTRACTS = ["burrow.near", "contract.main.burrow.near"]
BRIDGE_CONTRACTS = ["aurora", "rainbow-bridge", "factory.bridge.near"]


def get_near_rules() -> list:
    """Return NEAR classification rules derived from tax/categories.py patterns.

    Each rule is a dict compatible with the classification_rules table schema:
        name (str): unique human-readable identifier
        chain (str): 'near'
        pattern (dict): JSONB-compatible matching criteria
        category (str): TaxCategory value string
        confidence (float): 0.0–1.0
        priority (int): higher = checked first

    Rules derived from categorize_near_transaction() in tax/categories.py.
    """
    rules = []

    # -----------------------------------------------------------------------
    # STAKING — priority 100
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_staking_deposit",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["deposit_and_stake", "stake", "deposit"],
            "counterparty_suffix": STAKING_CONTRACTS,
        },
        "category": "stake",
        "confidence": 0.95,
        "priority": 100,
    })

    rules.append({
        "name": "near_unstaking",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["unstake", "unstake_all"],
            "counterparty_suffix": STAKING_CONTRACTS,
        },
        "category": "unstake",
        "confidence": 0.95,
        "priority": 100,
    })

    rules.append({
        "name": "near_staking_withdrawal",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["withdraw", "withdraw_all"],
            "counterparty_suffix": STAKING_CONTRACTS,
        },
        "category": "unstake",
        "confidence": 0.90,
        "priority": 100,
    })

    rules.append({
        "name": "near_validator_ping",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["ping"],
            "counterparty_suffix": STAKING_CONTRACTS,
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 100,
    })

    rules.append({
        "name": "near_staking_reward",
        "chain": "near",
        "pattern": {
            "direction": "in",
            "amount_gt": 0,
            "counterparty_suffix": STAKING_CONTRACTS,
        },
        "category": "reward",
        "confidence": 0.85,
        "priority": 100,
    })

    # -----------------------------------------------------------------------
    # DEX / SWAPS — priority 90
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_dex_swap_out",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["swap", "ft_transfer_call"],
            "direction": "out",
            "counterparty_in": DEX_CONTRACTS,
        },
        "category": "trade",
        "confidence": 0.90,
        "priority": 90,
    })

    rules.append({
        "name": "near_dex_swap_in",
        "chain": "near",
        "pattern": {
            "direction": "in",
            "amount_gt": 0,
            "counterparty_in": DEX_CONTRACTS,
        },
        "category": "trade",
        "confidence": 0.85,
        "priority": 90,
    })

    # -----------------------------------------------------------------------
    # LENDING / BURROW — priority 80
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_lending_deposit",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["supply", "deposit"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "collateral_in",
        "confidence": 0.90,
        "priority": 80,
    })

    rules.append({
        "name": "near_lending_withdrawal",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["withdraw"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "collateral_out",
        "confidence": 0.90,
        "priority": 80,
    })

    rules.append({
        "name": "near_borrow",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["borrow"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "loan_borrow",
        "confidence": 0.90,
        "priority": 80,
    })

    rules.append({
        "name": "near_loan_repay",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["repay"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "loan_repay",
        "confidence": 0.90,
        "priority": 80,
    })

    rules.append({
        "name": "near_lending_interest",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["claim_reward"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "interest",
        "confidence": 0.85,
        "priority": 80,
    })

    # -----------------------------------------------------------------------
    # LP / LIQUIDITY — priority 70
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_lp_add",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["add_liquidity", "add_stable_liquidity"],
            "counterparty_in": DEX_CONTRACTS,
        },
        "category": "liquidity_in",
        "confidence": 0.90,
        "priority": 70,
    })

    rules.append({
        "name": "near_lp_remove",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["remove_liquidity"],
            "counterparty_in": DEX_CONTRACTS,
        },
        "category": "liquidity_out",
        "confidence": 0.90,
        "priority": 70,
    })

    # -----------------------------------------------------------------------
    # NFT — priority 60
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_nft_mint",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["nft_mint", "nft_mint_batch"],
        },
        "category": "nft_mint",
        "confidence": 0.95,
        "priority": 60,
    })

    # -----------------------------------------------------------------------
    # AIRDROPS — priority 60
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_airdrop_claim",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["claim", "claim_airdrop", "claim_tokens"],
        },
        "category": "airdrop",
        "confidence": 0.85,
        "priority": 60,
    })

    # -----------------------------------------------------------------------
    # EPOCH STAKING REWARDS (system account) — priority 95
    # On NEAR, validator epoch rewards are native TRANSFERs from "system"
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_system_staking_reward",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_exact": "system",
        },
        "category": "reward",
        "confidence": 0.99,
        "priority": 95,
    })

    # -----------------------------------------------------------------------
    # FARMING REWARDS — priority 85
    # Ref Finance boost farming, LP farming, and other reward claims
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_farming_claim_reward",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["claim_reward_by_seed", "account_farm_claim_all",
                            "withdraw_reward", "claim_reward"],
        },
        "category": "reward",
        "confidence": 0.95,
        "priority": 85,
    })

    # -----------------------------------------------------------------------
    # wNEAR WRAP/UNWRAP — priority 85
    # wrap.near near_deposit = wrapping NEAR, near_withdraw = unwrapping
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_wnear_wrap",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["near_deposit"],
            "counterparty_exact": "wrap.near",
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 85,
    })

    rules.append({
        "name": "near_wnear_unwrap",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["near_withdraw"],
            "counterparty_exact": "wrap.near",
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 85,
    })

    # Inbound TRANSFER from wrap.near = wNEAR unwrap receipt
    rules.append({
        "name": "near_wnear_unwrap_receipt",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_exact": "wrap.near",
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 85,
    })

    # -----------------------------------------------------------------------
    # LENDING REWARDS (Burrow) — priority 85
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_burrow_oracle_call",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["oracle_call"],
            "counterparty_exact": "priceoracle.near",
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 85,
    })

    rules.append({
        "name": "near_burrow_execute_pyth",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["execute_with_pyth"],
            "counterparty_in": LENDING_CONTRACTS,
        },
        "category": "internal",
        "confidence": 0.95,
        "priority": 85,
    })

    # -----------------------------------------------------------------------
    # DEX INTENTS — priority 85
    # intents.near is NEAR's intent-based swap system
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_intents_swap_receipt",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_exact": "intents.near",
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 85,
    })

    # -----------------------------------------------------------------------
    # DEX SWAP RECEIPTS — priority 85
    # Inbound TRANSFERs from known DEX contracts = swap output
    # -----------------------------------------------------------------------
    DEX_CONTRACTS_EXTENDED = DEX_CONTRACTS + [
        "dclv2.ref-labs.near", "dcl.ref-labs.near",
    ]
    rules.append({
        "name": "near_dex_swap_receipt",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_in": DEX_CONTRACTS_EXTENDED,
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 85,
    })

    # -----------------------------------------------------------------------
    # LIQUID STAKING — priority 80
    # meta-pool.near, linear-protocol.near
    # -----------------------------------------------------------------------
    LIQUID_STAKING_CONTRACTS = ["meta-pool.near", "linear-protocol.near"]
    rules.append({
        "name": "near_liquid_staking_receipt",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_in": LIQUID_STAKING_CONTRACTS,
        },
        "category": "unstake",
        "confidence": 0.90,
        "priority": 80,
    })

    # -----------------------------------------------------------------------
    # INSCRIPTION OPS — priority 70
    # inscription.near inscribe method = NFT-like, non-taxable
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_inscription",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["inscribe"],
            "counterparty_exact": "inscription.near",
        },
        "category": "internal",
        "confidence": 0.95,
        "priority": 70,
    })

    # -----------------------------------------------------------------------
    # DID / SOCIAL — priority 60
    # social.near, did.near: non-financial identity/social operations
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_social_operations",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["set"],
            "counterparty_exact": "social.near",
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 60,
    })

    rules.append({
        "name": "near_did_operations",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["storeAlias", "storeSchema", "storeDefinition",
                            "deleteSchema", "deleteDefinition", "putDID"],
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 60,
    })

    # -----------------------------------------------------------------------
    # DAO PAYOUTS — priority 55
    # *.cdao.near and *.sputnikdao.near inbound transfers = income/bounty
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_dao_payout",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_suffix": [".cdao.near", ".sputnikdao.near"],
        },
        "category": "income",
        "confidence": 0.90,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # VOTING / GOVERNANCE — priority 55
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_voting",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["vote", "act_proposal"],
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # TRANSFER TO OTHER PERSON — priority 55
    # transfer_near method (e.g. to transfer-near.near) = outbound transfer
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_transfer_near_method",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["transfer_near"],
        },
        "category": "withdrawal",
        "confidence": 0.90,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # MFT TRANSFER CALL — priority 55
    # Multi-fungible token transfer (DEX LP shares, etc.)
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_mft_transfer_call",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["mft_transfer_call"],
        },
        "category": "trade",
        "confidence": 0.85,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # DELTA TRADE — priority 55
    # Inbound transfers from grid trading bots
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_deltatrade_receipt",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_suffix": [".deltatrade.near"],
        },
        "category": "trade",
        "confidence": 0.90,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # NF-PAYMENTS — priority 55
    # nf-payments.near, nf-finance.near = NFT marketplace payouts
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_nf_payout",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
            "counterparty_in": ["nf-payments.near", "nf-finance.near"],
        },
        "category": "nft_sale",
        "confidence": 0.85,
        "priority": 55,
    })

    # -----------------------------------------------------------------------
    # FT TRANSFERS (own wallet) — priority 50
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_ft_transfer_in_own",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["ft_transfer", "ft_transfer_call"],
            "direction": "in",
            "is_own_wallet": True,
        },
        "category": "transfer_in",
        "confidence": 0.90,
        "priority": 50,
    })

    rules.append({
        "name": "near_ft_transfer_out_own",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["ft_transfer", "ft_transfer_call"],
            "direction": "out",
            "is_own_wallet": True,
        },
        "category": "transfer_out",
        "confidence": 0.90,
        "priority": 50,
    })

    # -----------------------------------------------------------------------
    # BASIC NEAR TRANSFERS — priority 50
    # After all specific counterparty rules above, remaining inbound
    # TRANSFERs are genuine deposits from unknown external addresses.
    # Confidence raised to 0.90 since all known special cases handled above.
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_transfer_in",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "in",
        },
        "category": "deposit",
        "confidence": 0.90,
        "priority": 50,
    })

    rules.append({
        "name": "near_transfer_out",
        "chain": "near",
        "pattern": {
            "action_type": "TRANSFER",
            "direction": "out",
        },
        "category": "withdrawal",
        "confidence": 0.90,
        "priority": 50,
    })

    # -----------------------------------------------------------------------
    # ACCOUNT OPERATIONS — priority 50
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_account_create",
        "chain": "near",
        "pattern": {
            "action_type": "CREATE_ACCOUNT",
        },
        "category": "account_create",
        "confidence": 0.95,
        "priority": 50,
    })

    rules.append({
        "name": "near_key_management",
        "chain": "near",
        "pattern": {
            "action_type": ["ADD_KEY", "DELETE_KEY"],
        },
        "category": "internal",
        "confidence": 0.99,
        "priority": 50,
    })

    # -----------------------------------------------------------------------
    # STORAGE — priority 50
    # -----------------------------------------------------------------------
    rules.append({
        "name": "near_storage_ops",
        "chain": "near",
        "pattern": {
            "action_type": "FUNCTION_CALL",
            "method_name": ["storage_deposit", "storage_withdraw"],
        },
        "category": "fee",
        "confidence": 0.90,
        "priority": 50,
    })

    return rules


def get_evm_rules() -> list:
    """Return EVM classification rules derived from EVMDecoder signature tables.

    Ports EVMDecoder.DEX_SIGNATURES, LENDING_SIGNATURES, and LP_SIGNATURES
    into database rules so the classifier can match without importing the decoder.

    Each rule matches on the 4-byte method selector in raw_data.input.
    """
    decoder = EVMDecoder()
    rules = []

    # -----------------------------------------------------------------------
    # DEX SWAPS — priority 90 (all 10 Uniswap V2/V3 selectors)
    # -----------------------------------------------------------------------
    for selector, method_name in decoder.DEX_SIGNATURES.items():
        v3_methods = {"exactInputSingle", "exactInput", "exactOutputSingle", "exactOutput"}
        dex_type = "uniswap_v3" if method_name in v3_methods else "uniswap_v2"
        rules.append({
            "name": f"evm_dex_swap_{method_name.lower()}",
            "chain": "evm",
            "pattern": {
                "input_selector": selector,
                "method_name": method_name,
                "dex_type": dex_type,
            },
            "category": "trade",
            "confidence": 0.90,
            "priority": 90,
        })

    # -----------------------------------------------------------------------
    # LENDING (Aave V2) — priority 80
    # -----------------------------------------------------------------------
    lending_categories = {
        "deposit": "collateral_in",
        "withdraw": "collateral_out",
        "borrow": "loan_borrow",
        "repay": "loan_repay",
        "flashLoan": "loan_borrow",
    }
    for selector, method_name in decoder.LENDING_SIGNATURES.items():
        category = lending_categories.get(method_name, "unknown")
        rules.append({
            "name": f"evm_lending_{method_name.lower()}",
            "chain": "evm",
            "pattern": {
                "input_selector": selector,
                "method_name": method_name,
                "protocol": "aave_v2",
            },
            "category": category,
            "confidence": 0.85,
            "priority": 80,
        })

    # -----------------------------------------------------------------------
    # LP OPERATIONS — priority 70
    # -----------------------------------------------------------------------
    lp_categories = {
        "addLiquidity": "liquidity_in",
        "addLiquidityETH": "liquidity_in",
        "removeLiquidity": "liquidity_out",
        "removeLiquidityETH": "liquidity_out",
        "removeLiquidityETHSupportingFeeOnTransferTokens": "liquidity_out",
        "removeLiquidityWithPermit": "liquidity_out",
    }
    for selector, method_name in decoder.LP_SIGNATURES.items():
        category = lp_categories.get(method_name, "liquidity_in")
        rules.append({
            "name": f"evm_lp_{method_name.lower()}",
            "chain": "evm",
            "pattern": {
                "input_selector": selector,
                "method_name": method_name,
                "protocol": "uniswap_v2",
            },
            "category": category,
            "confidence": 0.85,
            "priority": 70,
        })

    # -----------------------------------------------------------------------
    # PLAIN EVM TRANSFERS (no input data) — priority 50
    # -----------------------------------------------------------------------
    rules.append({
        "name": "evm_plain_transfer_in",
        "chain": "evm",
        "pattern": {
            "input_selector": None,
            "direction": "in",
        },
        "category": "deposit",
        "confidence": 0.70,
        "priority": 50,
    })

    rules.append({
        "name": "evm_plain_transfer_out",
        "chain": "evm",
        "pattern": {
            "input_selector": None,
            "direction": "out",
        },
        "category": "withdrawal",
        "confidence": 0.70,
        "priority": 50,
    })

    return rules


def get_exchange_rules() -> list:
    """Return exchange transaction classification rules.

    Ports from classify_exchange_transaction() in engine/classifier.py.
    Chain value 'exchange' matches exchange_transactions table records.
    """
    rules = []

    # -----------------------------------------------------------------------
    # ACQUISITIONS — priority 40
    # -----------------------------------------------------------------------
    rules.append({
        "name": "exchange_buy",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["buy", "purchase"],
        },
        "category": "buy",
        "confidence": 0.95,
        "priority": 40,
    })

    # -----------------------------------------------------------------------
    # DISPOSITIONS — priority 40
    # -----------------------------------------------------------------------
    rules.append({
        "name": "exchange_sell",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["sell", "sale"],
        },
        "category": "sell",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_swap",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["swap", "convert", "trade"],
        },
        "category": "trade",
        "confidence": 0.95,
        "priority": 40,
    })

    # -----------------------------------------------------------------------
    # INCOME — priority 40
    # -----------------------------------------------------------------------
    rules.append({
        "name": "exchange_staking_reward",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["staking_reward"],
        },
        "category": "reward",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_interest",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["interest"],
        },
        "category": "interest",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_reward",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["reward"],
        },
        "category": "reward",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_dividend",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["dividend"],
        },
        "category": "income",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_airdrop",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["airdrop"],
        },
        "category": "airdrop",
        "confidence": 0.90,
        "priority": 40,
    })

    # -----------------------------------------------------------------------
    # TRANSFERS — priority 40
    # -----------------------------------------------------------------------
    rules.append({
        "name": "exchange_withdrawal",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["send", "withdrawal"],
        },
        "category": "withdrawal",
        "confidence": 0.80,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_deposit",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["receive", "deposit"],
        },
        "category": "deposit",
        "confidence": 0.80,
        "priority": 40,
    })

    # -----------------------------------------------------------------------
    # CRYPTO.COM SPECIFIC — priority 40
    # Crypto.com exports use non-standard tx_types for card/VIBAN operations
    # -----------------------------------------------------------------------
    rules.append({
        "name": "exchange_crypto_viban",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["crypto_viban"],
        },
        "category": "sell",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_crypto_viban_exchange",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["crypto_viban_exchange"],
        },
        "category": "trade",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_viban_deposit",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["viban_deposit", "viban_purchase"],
        },
        "category": "deposit",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_viban_withdrawal",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["viban_withdrawal"],
        },
        "category": "withdrawal",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_crypto_transfer_in",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["exchange_to_crypto_transfer", "crypto_transfer"],
        },
        "category": "transfer_in",
        "confidence": 0.85,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_crypto_earn_deposit",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["crypto_earn_program_created", "crypto_earn_program_deposit",
                        "lockup_lock"],
        },
        "category": "stake",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_crypto_earn_withdraw",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["crypto_earn_program_withdrawn", "crypto_earn_program_withdrawal",
                        "lockup_unlock"],
        },
        "category": "unstake",
        "confidence": 0.90,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_crypto_earn_interest",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["crypto_earn_interest_paid"],
        },
        "category": "interest",
        "confidence": 0.95,
        "priority": 40,
    })

    rules.append({
        "name": "exchange_referral_bonus",
        "chain": "exchange",
        "pattern": {
            "tx_type": ["referral_bonus", "referral_card_cashback",
                        "reimbursement", "card_cashback_reverted"],
        },
        "category": "reward",
        "confidence": 0.90,
        "priority": 40,
    })

    return rules


def seed_classification_rules(pool) -> int:
    """Insert all classification rules into the classification_rules table.

    Idempotent: uses INSERT ... ON CONFLICT (name) DO UPDATE so it can be
    run multiple times safely. The uq_cr_name unique constraint on
    classification_rules.name was created by migration 003.

    Args:
        pool: psycopg2 connection pool (ThreadedConnectionPool or similar).

    Returns:
        Number of rules inserted/updated.
    """
    rules = get_near_rules() + get_evm_rules() + get_exchange_rules()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        count = 0
        for rule in rules:
            cur.execute(
                """INSERT INTO classification_rules
                   (name, chain, pattern, category, confidence, priority,
                    is_active, created_at, updated_at)
                   VALUES (%s, %s, %s::jsonb, %s, %s, %s, TRUE, NOW(), NOW())
                   ON CONFLICT (name) DO UPDATE SET
                     pattern = EXCLUDED.pattern,
                     category = EXCLUDED.category,
                     confidence = EXCLUDED.confidence,
                     priority = EXCLUDED.priority,
                     updated_at = NOW()
                """,
                (
                    rule["name"],
                    rule["chain"],
                    json.dumps(rule["pattern"]),
                    rule["category"],
                    rule["confidence"],
                    rule["priority"],
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        pool.putconn(conn)
