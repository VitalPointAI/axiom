"""SSE streaming endpoint for real-time wallet transaction updates.

Endpoint:
  GET /api/stream/wallet/{wallet_id} — SSE stream using PostgreSQL LISTEN/NOTIFY

Implementation:
  Opens a dedicated psycopg2 connection (NOT from the pool — it is long-lived).
  Sets AUTOCOMMIT isolation and issues LISTEN new_transactions.
  Uses select.select() for non-blocking polling with 5-second timeout.
  On notification: parses payload JSON, filters by wallet_id, yields SSE event.
  On timeout: yields keepalive comment to keep connection alive.
  On client disconnect: finally block closes the dedicated connection.

Optional ?since_block=N query parameter replays recent transactions from the
transactions table before starting the live stream.

SSE event format:
    data: {"wallet_id": 42, "tx_hash": "abc", ...}\n\n

Keepalive format (every 5s if no events):
    : keepalive\n\n
"""

import json
import logging
import select

import psycopg2
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.dependencies import get_current_user, get_pool_dep
from config import DATABASE_URL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])

# SSE constants
SSE_POLL_TIMEOUT = 5.0  # seconds between keepalives
KEEPALIVE_COMMENT = ": keepalive\n\n"
LISTEN_CHANNEL = "new_transactions"


# ---------------------------------------------------------------------------
# SSE helper functions (exported for unit testing)
# ---------------------------------------------------------------------------


def _build_sse_event(payload: dict) -> str:
    """Build a properly formatted SSE data event string.

    Args:
        payload: Dict to serialize as JSON in the SSE event.

    Returns:
        SSE-formatted string ending with double newline.
    """
    return f"data: {json.dumps(payload)}\n\n"


def _matches_wallet(payload: dict, wallet_id: int) -> bool:
    """Check if a pg_notify payload matches the requested wallet_id.

    Handles both string and integer wallet_id values in the payload,
    since JSON serialization may produce either type.

    Args:
        payload: Parsed JSON payload dict from pg_notify.
        wallet_id: The wallet_id to filter for.

    Returns:
        True if the payload's wallet_id matches.
    """
    payload_wallet_id = payload.get("wallet_id")
    if payload_wallet_id is None:
        return False
    try:
        return int(payload_wallet_id) == wallet_id
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# SSE stream generator
# ---------------------------------------------------------------------------


def _sse_stream(wallet_id: int, since_block: int, user_id: int, pool):
    """Generator that yields SSE events for wallet transaction updates.

    Opens a dedicated psycopg2 connection for LISTEN/NOTIFY.
    Replays recent transactions since since_block before starting live stream.
    Polls every SSE_POLL_TIMEOUT seconds and yields keepalive on timeout.

    Args:
        wallet_id: DB wallet id to filter notifications for.
        since_block: Block height to replay from (0 = no replay).
        user_id: Authenticated user id for ownership check.
        pool: psycopg2 connection pool (used for initial ownership check only).

    Yields:
        SSE-formatted string chunks.
    """
    # Verify wallet ownership before starting stream
    conn_check = pool.getconn()
    try:
        cur = conn_check.cursor()
        cur.execute(
            "SELECT id FROM wallets WHERE id = %s AND user_id = %s",
            (wallet_id, user_id),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn_check)

    if row is None:
        # Yield an error event and stop
        yield f"data: {json.dumps({'error': 'Wallet not found', 'wallet_id': wallet_id})}\n\n"
        return

    # Replay recent transactions if since_block provided
    if since_block > 0:
        conn_replay = pool.getconn()
        try:
            cur = conn_replay.cursor()
            cur.execute(
                """
                SELECT tx_hash, block_timestamp, action_type, token_id, amount, chain
                FROM transactions
                WHERE wallet_id = %s AND user_id = %s
                  AND raw_data->>'ledger_index' IS NOT NULL
                  AND (raw_data->>'ledger_index')::bigint > %s
                ORDER BY block_timestamp ASC
                LIMIT 100
                """,
                (wallet_id, user_id, since_block),
            )
            rows = cur.fetchall()
            cur.close()
            for row in rows:
                tx_hash, block_timestamp, action_type, token_id, amount, chain = row
                payload = {
                    "wallet_id": wallet_id,
                    "tx_hash": tx_hash,
                    "block_timestamp": str(block_timestamp) if block_timestamp else None,
                    "action_type": action_type,
                    "token_id": token_id,
                    "amount": str(amount) if amount else None,
                    "chain": chain,
                    "replay": True,
                }
                yield _build_sse_event(payload)
        except Exception:
            logger.warning("SSE replay failed for wallet_id=%s", wallet_id, exc_info=True)
        finally:
            pool.putconn(conn_replay)

    # Open dedicated long-lived connection for LISTEN
    if not DATABASE_URL:
        yield f"data: {json.dumps({'error': 'DATABASE_URL not configured'})}\n\n"
        return

    listen_conn = psycopg2.connect(DATABASE_URL)
    try:
        listen_conn.autocommit = True
        cur = listen_conn.cursor()
        cur.execute(f"LISTEN {LISTEN_CHANNEL}")
        cur.close()
        logger.info("SSE stream started for wallet_id=%s user_id=%s", wallet_id, user_id)

        while True:
            # Non-blocking poll with timeout
            readable, _, _ = select.select([listen_conn], [], [], SSE_POLL_TIMEOUT)
            if not readable:
                # Timeout — send keepalive
                yield KEEPALIVE_COMMENT
                continue

            # Process any pending notifications
            listen_conn.poll()
            while listen_conn.notifies:
                notify = listen_conn.notifies.pop(0)
                try:
                    payload = json.loads(notify.payload)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("SSE: invalid JSON payload from pg_notify: %s", notify.payload)
                    continue

                if _matches_wallet(payload, wallet_id):
                    yield _build_sse_event(payload)

    except GeneratorExit:
        logger.info("SSE client disconnected for wallet_id=%s", wallet_id)
    except Exception:
        logger.warning("SSE stream error for wallet_id=%s", wallet_id, exc_info=True)
    finally:
        try:
            listen_conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GET /api/stream/wallet/{wallet_id}
# ---------------------------------------------------------------------------


@router.get("/wallet/{wallet_id}")
async def stream_wallet_updates(
    wallet_id: int,
    since_block: int = Query(default=0, ge=0, description="Replay transactions since this block height"),
    user: dict = Depends(get_current_user),
    pool=Depends(get_pool_dep),
):
    """Stream real-time wallet transaction updates via Server-Sent Events.

    Uses PostgreSQL LISTEN/NOTIFY on the 'new_transactions' channel.
    The indexer must NOTIFY new_transactions with a JSON payload containing
    at least wallet_id and tx_hash for the stream to deliver events.

    Query params:
        since_block: Optional block height to replay recent transactions before
                     starting the live stream.

    SSE events:
        data: {"wallet_id": N, "tx_hash": "...", "chain": "...", ...}

    Keepalive (every 5s if no new transactions):
        : keepalive
    """
    user_id = user["user_id"]

    return StreamingResponse(
        _sse_stream(wallet_id, since_block, user_id, pool),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
