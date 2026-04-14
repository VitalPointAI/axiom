"""Report generation, preview, download, and status endpoints.

Endpoints:
  POST /api/reports/generate         — queue generate_reports job
  GET  /api/reports/preview/{type}   — inline data preview (LIMIT 50)
  GET  /api/reports/download/{year}  — list files in tax package directory
  GET  /api/reports/download/{year}/{filename} — serve file via FileResponse
  GET  /api/reports/status           — check if reports exist for year

Report generation uses the job queue pattern:
  - Inserts a generate_reports job with cursor JSON
  - Frontend polls /api/jobs/{id}/status for completion
  - On completion, calls /api/reports/download/{year} to list downloadable files

Preview endpoints run lightweight DB queries (LIMIT 50) so the UI can show
inline data before the full report package is generated.

File downloads use FastAPI's FileResponse to stream files from disk.
Path traversal is prevented by checking that the resolved path stays inside
the expected tax_package directory.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from api.dependencies import get_effective_user_with_dek, get_pool_dep
from api.rate_limit import limiter
from api.schemas.reports import (
    ExchangeImportResponse,
    ReportFileInfo,
    ReportFileResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportPreviewResponse,
    ReportStatusResponse,
    SupportedExchange,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])
exchanges_router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])

# ---------------------------------------------------------------------------
# Valid preview report types
# ---------------------------------------------------------------------------

_VALID_PREVIEW_TYPES = {
    "capital-gains",
    "income",
    "ledger",
    "t1135",
    "superficial-losses",
    "holdings",
}


# ---------------------------------------------------------------------------
# Helper: resolve output directory root
# ---------------------------------------------------------------------------


def _get_output_dir() -> str:
    """Return the root output directory for tax packages.

    Override this in tests by patching 'api.routers.reports._get_output_dir'.
    """
    return os.path.join(os.getcwd(), "output")


# ---------------------------------------------------------------------------
# Helper: check report staleness
# ---------------------------------------------------------------------------


def _check_staleness(output_dir: str, conn, user_id: int):
    """Compare MANIFEST.json fingerprint against current DB state.

    Returns:
        {"stale": False} if fingerprint matches.
        {"stale": True, "stale_reason": str, "changed_fields": list} if fingerprint differs.
        None if no MANIFEST.json exists in output_dir.
    """
    from reports.generate import get_data_fingerprint

    manifest_path = Path(output_dir) / "MANIFEST.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    stored = manifest.get("source_data_version", {})
    current = get_data_fingerprint(conn, user_id)

    changed_fields = [
        k for k in ("last_tx_timestamp", "total_tx_count", "acb_snapshot_version", "needs_review_count")
        if stored.get(k) != current.get(k)
    ]

    if changed_fields:
        return {
            "stale": True,
            "stale_reason": "Data has changed since this report was generated",
            "changed_fields": changed_fields,
        }
    return {"stale": False}


# ---------------------------------------------------------------------------
# POST /api/reports/generate
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=ReportGenerateResponse)
@limiter.limit("5/minute")
async def generate_report(
    request: Request,
    body: ReportGenerateRequest,
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Queue a generate_reports job for the given year.

    specialist_override=True bypasses the needs_review gate and is admin-only.
    Returns job_id for polling.
    """
    user_id = user["user_id"]

    # Admin gate for specialist override
    if body.specialist_override and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="specialist_override requires admin access",
        )

    cursor_json = json.dumps(
        {
            "year": body.year,
            "tax_treatment": body.tax_treatment,
            "specialist_override": body.specialist_override,
        }
    )

    def _queue(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO indexing_jobs (user_id, job_type, status, priority, cursor)
                VALUES (%s, 'generate_reports', 'queued', 5, %s)
                RETURNING id
                """,
                (user_id, cursor_json),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0]
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        job_id = await run_in_threadpool(_queue, conn)
    finally:
        pool.putconn(conn)

    return ReportGenerateResponse(job_id=job_id, status="queued")


# ---------------------------------------------------------------------------
# GET /api/reports/preview/{report_type}
# ---------------------------------------------------------------------------


@router.get("/preview/{report_type}", response_model=ReportPreviewResponse)
async def preview_report(
    report_type: str,
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return up to 50 rows of inline preview data for the given report type.

    Supported types: capital-gains, income, ledger, t1135, superficial-losses, holdings
    """
    if report_type not in _VALID_PREVIEW_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown report type '{report_type}'. Valid: {sorted(_VALID_PREVIEW_TYPES)}",
        )

    user_id = user["user_id"]

    def _preview(conn):
        cur = conn.cursor()
        try:
            if report_type == "capital-gains":
                cur.execute(
                    """
                    SELECT
                        disposal_date::text,
                        token_symbol,
                        quantity::text,
                        proceeds_cad::text,
                        acb_cad::text,
                        net_gain_loss::text
                    FROM capital_gains_ledger
                    WHERE user_id = %s
                    ORDER BY disposal_date
                    LIMIT 50
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                keys = ["disposal_date", "token_symbol", "quantity", "proceeds_cad", "acb_cad", "net_gain_loss"]

            elif report_type == "income":
                cur.execute(
                    """
                    SELECT
                        token_symbol,
                        DATE_TRUNC('month', income_date)::text AS month,
                        SUM(amount)::text,
                        SUM(fmv_cad)::text
                    FROM income_ledger
                    WHERE user_id = %s
                    GROUP BY token_symbol, DATE_TRUNC('month', income_date)
                    ORDER BY month
                    LIMIT 50
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                keys = ["token_symbol", "month", "amount", "fmv_cad"]

            elif report_type == "ledger":
                # UNION ALL of on-chain + exchange transactions
                cur.execute(
                    """
                    SELECT
                        tx_date::text,
                        account_id,
                        tx_type,
                        amount::text,
                        token_symbol,
                        'near' AS source
                    FROM transactions t
                    JOIN wallets w ON w.id = t.wallet_id
                    WHERE w.user_id = %s
                    UNION ALL
                    SELECT
                        tx_date::text,
                        exchange_id AS account_id,
                        tx_type,
                        amount::text,
                        asset AS token_symbol,
                        'exchange' AS source
                    FROM exchange_transactions
                    WHERE user_id = %s
                    ORDER BY tx_date
                    LIMIT 50
                    """,
                    (user_id, user_id),
                )
                rows = cur.fetchall()
                keys = ["tx_date", "account_id", "tx_type", "amount", "token_symbol", "source"]

            elif report_type == "t1135":
                cur.execute(
                    """
                    SELECT
                        token_symbol,
                        MAX(total_cost_cad)::text AS peak_cost_cad,
                        chain
                    FROM acb_snapshots
                    WHERE user_id = %s
                    GROUP BY token_symbol, chain
                    ORDER BY token_symbol
                    LIMIT 50
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                keys = ["token_symbol", "peak_cost_cad", "chain"]

            elif report_type == "superficial-losses":
                cur.execute(
                    """
                    SELECT
                        disposal_date::text,
                        token_symbol,
                        quantity::text,
                        net_gain_loss::text,
                        denied_loss::text
                    FROM capital_gains_ledger
                    WHERE user_id = %s
                      AND is_superficial_loss = TRUE
                    ORDER BY disposal_date
                    LIMIT 50
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                keys = ["disposal_date", "token_symbol", "quantity", "net_gain_loss", "denied_loss"]

            elif report_type == "holdings":
                cur.execute(
                    """
                    SELECT
                        token_symbol,
                        quantity::text,
                        acb_per_unit::text,
                        total_cost_cad::text,
                        chain
                    FROM (
                        SELECT
                            token_symbol,
                            quantity,
                            acb_per_unit,
                            total_cost_cad,
                            chain,
                            ROW_NUMBER() OVER (
                                PARTITION BY token_symbol
                                ORDER BY as_of_date DESC
                            ) AS rn
                        FROM acb_snapshots
                        WHERE user_id = %s
                    ) ranked
                    WHERE rn = 1
                    ORDER BY token_symbol
                    LIMIT 50
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                keys = ["token_symbol", "quantity", "acb_per_unit", "total_cost_cad", "chain"]

            else:
                rows = []
                keys = []

            return [dict(zip(keys, r)) for r in rows]
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_preview, conn)
    finally:
        pool.putconn(conn)

    return ReportPreviewResponse(
        report_type=report_type,
        rows=rows,
        total=len(rows),
    )


# ---------------------------------------------------------------------------
# GET /api/reports/download/{year} — list files
# ---------------------------------------------------------------------------


@router.get("/download/{year}", response_model=ReportFileResponse)
async def list_report_files(
    year: int,
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """List all files in the output/{year}_tax_package/ directory.

    Returns file names, sizes, and download URLs.
    Returns 404 if the directory does not exist.
    Includes stale=True/False when MANIFEST.json is present.
    """
    output_root = _get_output_dir()
    pkg_dir = Path(output_root) / f"{year}_tax_package"

    if not pkg_dir.exists() or not pkg_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report package found for year {year}",
        )

    files = []
    for entry in sorted(pkg_dir.iterdir()):
        if entry.is_file():
            files.append(
                ReportFileInfo(
                    name=entry.name,
                    size=entry.stat().st_size,
                    url=f"/api/reports/download/{year}/{entry.name}",
                )
            )

    user_id = user["user_id"]

    def _stale_check(conn):
        return _check_staleness(str(pkg_dir), conn, user_id)

    conn = pool.getconn()
    try:
        staleness = await run_in_threadpool(_stale_check, conn)
    finally:
        pool.putconn(conn)

    if staleness is not None:
        from fastapi.responses import JSONResponse
        response_dict = ReportFileResponse(year=year, files=files).model_dump()
        response_dict["stale"] = staleness["stale"]
        if staleness.get("stale"):
            response_dict["stale_reason"] = staleness.get("stale_reason", "")
        return JSONResponse(content=response_dict)

    return ReportFileResponse(year=year, files=files)


# ---------------------------------------------------------------------------
# GET /api/reports/download/{year}/{filename} — serve file
# ---------------------------------------------------------------------------


@router.get("/download/{year}/{filename}")
async def download_report_file(
    year: int,
    filename: str,
    user: dict = Depends(get_effective_user_with_dek),
):
    """Serve a report file from the output/{year}_tax_package/ directory.

    Validates the filename to prevent path traversal attacks.
    Returns 400 if the filename looks like a traversal attempt.
    Returns 404 if the file does not exist.
    """
    # Path traversal guard: filename must not contain path separators or '..'
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    output_root = _get_output_dir()
    pkg_dir = Path(output_root) / f"{year}_tax_package"
    file_path = pkg_dir / filename

    # Double-check resolved path is inside pkg_dir (guards against symlink attacks)
    real_path = os.path.realpath(str(file_path))
    real_pkg_dir = os.path.realpath(str(pkg_dir))
    if not real_path.startswith(real_pkg_dir + os.sep) and real_path != real_pkg_dir:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid filename",
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' not found for year {year}",
        )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# GET /api/reports/status — check if reports exist
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ReportStatusResponse)
async def report_status(
    year: int = Query(..., ge=1900, le=2200),
    user: dict = Depends(get_effective_user_with_dek),
):
    """Check whether a generated tax package exists for the given year."""
    output_root = _get_output_dir()
    pkg_dir = Path(output_root) / f"{year}_tax_package"

    if not pkg_dir.exists() or not pkg_dir.is_dir():
        return ReportStatusResponse(year=year, exists=False, file_count=0)

    files = [e for e in pkg_dir.iterdir() if e.is_file()]
    return ReportStatusResponse(year=year, exists=len(files) > 0, file_count=len(files))


# ---------------------------------------------------------------------------
# POST /api/exchanges/import
# ---------------------------------------------------------------------------


@exchanges_router.post("/import", response_model=ExchangeImportResponse)
async def import_exchange_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Accept a CSV exchange file upload, record it in file_imports, and queue a file_import job.

    Computes SHA-256 hash of the file content for deduplication.
    Stores the file content in the file_imports table and queues a file_import job.
    """
    user_id = user["user_id"]
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    original_filename = file.filename or "upload.csv"
    file_size = len(content)

    # Save file to disk so the indexer file_handler can read it
    upload_dir = Path(os.environ.get("UPLOAD_DIR", "uploads")) / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = str(upload_dir / f"{file_hash}_{original_filename}")
    with open(storage_path, "wb") as f:
        f.write(content)

    def _insert(conn):
        cur = conn.cursor()
        try:
            # Get or create the per-user virtual exchange wallet
            exchange_account_id = f"exchange_imports_{user_id}"
            cur.execute(
                """
                INSERT INTO wallets (user_id, account_id, chain)
                VALUES (%s, %s, 'exchange')
                ON CONFLICT (user_id, account_id, chain) DO NOTHING
                RETURNING id
                """,
                (user_id, exchange_account_id),
            )
            row = cur.fetchone()
            if row is None:
                # Already exists — look it up
                cur.execute(
                    "SELECT id FROM wallets WHERE user_id = %s AND account_id = %s AND chain = 'exchange'",
                    (user_id, exchange_account_id),
                )
                row = cur.fetchone()
            wallet_id = row[0]

            # Insert file_imports record
            cur.execute(
                """
                INSERT INTO file_imports (user_id, filename, file_hash, file_size, storage_path, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (user_id, file_hash) DO UPDATE
                    SET filename = EXCLUDED.filename,
                        storage_path = EXCLUDED.storage_path,
                        status = 'pending'
                RETURNING id
                """,
                (user_id, original_filename, file_hash, file_size, storage_path),
            )
            file_import_row = cur.fetchone()
            file_import_id = file_import_row[0]

            # Queue file_import job with file_import_id as cursor
            cur.execute(
                """
                INSERT INTO indexing_jobs (wallet_id, user_id, job_type, chain, status, priority, cursor)
                VALUES (%s, %s, 'file_import', 'exchange', 'queued', 6, %s)
                RETURNING id
                """,
                (wallet_id, user_id, str(file_import_id)),
            )
            job_row = cur.fetchone()
            job_id = job_row[0]

            conn.commit()
            return file_import_id, job_id
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        file_import_id, job_id = await run_in_threadpool(_insert, conn)
    finally:
        pool.putconn(conn)

    return ExchangeImportResponse(
        job_id=job_id,
        file_import_id=file_import_id,
        status="queued",
    )


# ---------------------------------------------------------------------------
# GET /api/exchanges — list supported exchanges
# ---------------------------------------------------------------------------


@exchanges_router.get("", response_model=List[SupportedExchange])
async def list_exchanges(
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return all supported exchanges from the supported_exchanges table."""

    def _list(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT slug, name, accepts_csv
                FROM supported_exchanges
                ORDER BY name
                """
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_list, conn)
    finally:
        pool.putconn(conn)

    return [
        SupportedExchange(slug=row[0], name=row[1], accepts_csv=bool(row[2]))
        for row in rows
    ]
