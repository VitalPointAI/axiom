"""
Sample Etherscan V2 API JSON responses for unit testing EVMFetcher.

All addresses, hashes, and values are synthetic test data.
"""

# ---------------------------------------------------------------------------
# Normal transaction (ETH transfer)
# ---------------------------------------------------------------------------

NORMAL_TX = {
    "blockNumber": "17500000",
    "timeStamp": "1688000000",
    "hash": "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1",
    "nonce": "42",
    "blockHash": "0x111aaa",
    "transactionIndex": "3",
    "from": "0xCOUNTERPARTY0000000000000000000000000000",
    "to": "0xWALLET000000000000000000000000000000000",
    "value": "1000000000000000000",  # 1 ETH in wei
    "gas": "21000",
    "gasPrice": "20000000000",  # 20 Gwei
    "isError": "0",
    "txreceipt_status": "1",
    "input": "0x",
    "contractAddress": "",
    "cumulativeGasUsed": "21000",
    "gasUsed": "21000",
    "confirmations": "500000",
    "methodId": "0x",
    "functionName": "",
}

NORMAL_TX_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [NORMAL_TX],
}

# ---------------------------------------------------------------------------
# ERC20 token transfer
# ---------------------------------------------------------------------------

ERC20_TX = {
    "blockNumber": "17500001",
    "timeStamp": "1688000015",
    "hash": "0xdef789abc012def789abc012def789abc012def789abc012def789abc012def7",
    "nonce": "43",
    "blockHash": "0x222bbb",
    "transactionIndex": "7",
    "from": "0xCOUNTERPARTY0000000000000000000000000000",
    "to": "0xWALLET000000000000000000000000000000000",
    "value": "500000000",  # 500 USDC (6 decimals)
    "contractAddress": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    "tokenName": "USD Coin",
    "tokenSymbol": "USDC",
    "tokenDecimal": "6",
    "gas": "65000",
    "gasPrice": "15000000000",
    "isError": "0",
    "txreceipt_status": "1",
    "input": "0xa9059cbb",
    "logIndex": "23",
    "gasUsed": "52000",
    "confirmations": "499999",
}

ERC20_TX_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [ERC20_TX],
}

# ---------------------------------------------------------------------------
# Internal transaction
# ---------------------------------------------------------------------------

INTERNAL_TX = {
    "blockNumber": "17500002",
    "timeStamp": "1688000030",
    "hash": "0x111222333444555666777888999aaabbbccc111222333444555666777888999a",
    "from": "0xCONTRACT00000000000000000000000000000000",
    "to": "0xWALLET000000000000000000000000000000000",
    "value": "250000000000000000",  # 0.25 ETH
    "contractAddress": "",
    "input": "",
    "type": "call",
    "gas": "2300",
    "gasUsed": "2300",
    "traceId": "0",
    "isError": "0",
    "errCode": "",
}

INTERNAL_TX_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [INTERNAL_TX],
}

# ---------------------------------------------------------------------------
# NFT (ERC721) transfer
# ---------------------------------------------------------------------------

NFT_TX = {
    "blockNumber": "17500003",
    "timeStamp": "1688000045",
    "hash": "0xnft111222333444555666777888999aaabbbccc111222333444555666777888",
    "nonce": "44",
    "blockHash": "0x333ccc",
    "transactionIndex": "2",
    "from": "0xWALLET000000000000000000000000000000000",
    "to": "0xBUYER00000000000000000000000000000000000",
    "contractAddress": "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D",  # BAYC
    "tokenID": "1234",
    "tokenName": "BoredApeYachtClub",
    "tokenSymbol": "BAYC",
    "tokenDecimal": "0",
    "gas": "120000",
    "gasPrice": "18000000000",
    "gasUsed": "85000",
    "isError": "0",
    "txreceipt_status": "1",
    "input": "0x",
    "logIndex": "5",
    "confirmations": "499997",
}

NFT_TX_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [NFT_TX],
}

# ---------------------------------------------------------------------------
# Empty responses
# ---------------------------------------------------------------------------

EMPTY_RESPONSE = {
    "status": "0",
    "message": "No transactions found",
    "result": [],
}

# ---------------------------------------------------------------------------
# Pagination fixture: two pages of results
# Used to test that _fetch_paginated loops when result count == page_size
# ---------------------------------------------------------------------------

def make_page(count: int, start_block: int = 17000000) -> dict:
    """Generate a response with `count` synthetic normal transactions."""
    results = []
    for i in range(count):
        results.append({
            "blockNumber": str(start_block + i),
            "timeStamp": str(1688000000 + i),
            "hash": f"0x{'a' * 62}{i:02d}",
            "from": "0xCOUNTERPARTY0000000000000000000000000000",
            "to": "0xWALLET000000000000000000000000000000000",
            "value": "1000000000000000",
            "gas": "21000",
            "gasPrice": "10000000000",
            "isError": "0",
            "txreceipt_status": "1",
            "gasUsed": "21000",
            "logIndex": str(i),
            "contractAddress": "",
        })
    return {"status": "1", "message": "OK", "result": results}


# ---------------------------------------------------------------------------
# Balance response
# ---------------------------------------------------------------------------

BALANCE_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": "5000000000000000000",  # 5 ETH in wei
}
