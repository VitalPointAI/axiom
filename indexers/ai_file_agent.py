"""AI-powered file ingestion agent for unknown exchange export files.

Uses the Anthropic Claude API to extract transaction data from any exchange
export file format (CSV, XLSX, PDF) that traditional parsers cannot handle.

Architecture:
- Known formats: routed to traditional ExchangeParser implementations
- Unknown formats: routed here to AIFileAgent for AI extraction
- All extracted transactions receive a confidence score (0.0-1.0)
- Transactions below CONFIDENCE_THRESHOLD are flagged needs_review=True
"""

import json
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.8  # Auto-commit above this, flag below

SYSTEM_PROMPT = """You are a financial transaction extractor. Given the contents of an exchange or financial platform export file, extract all transactions into a structured JSON array.

For each transaction, provide:
- tx_id: The exchange's transaction/order ID (or generate one from date+type+amount if none visible)
- tx_date: ISO 8601 format (YYYY-MM-DDTHH:MM:SS)
- tx_type: One of: buy, sell, send, receive, deposit, withdrawal, staking_reward, interest, fee, transfer, trade, airdrop, mining, other
- asset: The crypto asset symbol (BTC, ETH, NEAR, etc.)
- quantity: The amount as a decimal string
- price_per_unit: Price per unit in fiat (null if not available)
- total_value: Total fiat value (null if not available)
- fee: Fee amount (null if none)
- fee_asset: Fee currency/asset (null if none)
- currency: Fiat currency (CAD, USD, EUR, etc.)
- notes: Any relevant context
- confidence: Your confidence in this extraction (0.0-1.0)

Set confidence below 0.8 for: ambiguous transaction types, missing critical fields, unclear amounts, possible duplicate rows, or unfamiliar formats.

Respond with ONLY a JSON object: {"exchange": "detected_name", "transactions": [...]}"""


class AIFileAgent:
    """AI-powered file ingestion using Claude API.

    Handles unknown/complex exchange export files that traditional
    parsers cannot detect. Extracts transaction data with confidence
    scores and flags uncertain records for human review.

    Usage:
        agent = AIFileAgent(pool)
        result = agent.process_file(file_import_id=42, user_id=1)
        # result = {imported: 10, flagged: 2, errors: 0, exchange_detected: "Binance"}
    """

    def __init__(self, pool):
        self.pool = pool
        self._client = None  # Lazy init

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
        return self._client

    def process_file(self, file_import_id: int, user_id: int) -> dict:
        """Main entry point: process a queued file import using Claude AI.

        Loads file metadata from file_imports table, reads the file content,
        calls Claude API to extract transactions, and inserts them into
        exchange_transactions.

        Args:
            file_import_id: ID of the file_imports row to process
            user_id: ID of the user who owns this import

        Returns:
            dict with keys: imported, flagged, errors, exchange_detected
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT filename, storage_path FROM file_imports WHERE id = %s AND user_id = %s",
                (file_import_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                logger.error("file_import_id=%d not found for user_id=%d", file_import_id, user_id)
                return {"imported": 0, "flagged": 0, "errors": 1, "exchange_detected": None}

            filename, storage_path = row

            # Update status to processing
            cur.execute(
                "UPDATE file_imports SET status = 'processing' WHERE id = %s",
                (file_import_id,),
            )
            conn.commit()
        finally:
            self.pool.putconn(conn)

        # Read file content
        try:
            text_content = self._read_file_content(storage_path)
        except Exception as e:
            logger.error("Failed to read file %s: %s", storage_path, e)
            self._update_import_status(file_import_id, "failed", str(e))
            return {"imported": 0, "flagged": 0, "errors": 1, "exchange_detected": None}

        # Call Claude API to extract transactions
        try:
            transactions, exchange_detected = self._extract_transactions(text_content, filename)
        except Exception as e:
            logger.error("Claude API extraction failed for file_import_id=%d: %s", file_import_id, e)
            self._update_import_status(file_import_id, "failed", str(e))
            return {"imported": 0, "flagged": 0, "errors": 1, "exchange_detected": None}

        # Insert transactions into database
        result = self._insert_transactions(transactions, user_id, exchange_detected, file_import_id)

        # Update file_imports status
        status = "completed" if result["errors"] == 0 else "failed"
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE file_imports
                   SET status = %s, exchange_detected = %s,
                       rows_imported = %s, rows_skipped = %s, rows_flagged = %s
                   WHERE id = %s""",
                (
                    status,
                    exchange_detected,
                    result["imported"],
                    result.get("skipped", 0),
                    result["flagged"],
                    file_import_id,
                ),
            )
            conn.commit()
        finally:
            self.pool.putconn(conn)

        return {
            "imported": result["imported"],
            "flagged": result["flagged"],
            "errors": result["errors"],
            "exchange_detected": exchange_detected,
        }

    def _extract_transactions(self, text: str, filename: str) -> tuple:
        """Call Claude API to extract transactions from file text content.

        Args:
            text: file text content (may be truncated to 50k chars)
            filename: original filename (used as hint in user message)

        Returns:
            Tuple of (list of transaction dicts, exchange_name string)

        Raises:
            EnvironmentError: if ANTHROPIC_API_KEY is not set
            ValueError: if Claude returns unparseable response
        """
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Cannot use AI file agent."
            )

        user_message = (
            f"Please extract all transactions from this exchange export file.\n"
            f"Filename: {filename}\n\n"
            f"File contents:\n{text}"
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            raise

        raw_text = response.content[0].text.strip()

        # Parse the JSON response
        parsed = self._parse_json_response(raw_text)

        exchange_detected = parsed.get("exchange", "unknown")
        transactions = parsed.get("transactions", [])

        logger.info(
            "Claude extracted %d transactions from %s (exchange: %s)",
            len(transactions),
            filename,
            exchange_detected,
        )

        return transactions, exchange_detected

    def _parse_json_response(self, raw_text: str) -> dict:
        """Attempt to parse JSON from Claude's response.

        Tries direct parse first, then looks for JSON block within the text.

        Args:
            raw_text: raw text from Claude response

        Returns:
            Parsed dict with 'exchange' and 'transactions' keys

        Raises:
            ValueError: if JSON cannot be extracted
        """
        # Try direct parse first
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block within the text (e.g., wrapped in ```json ... ```)
        import re
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        logger.error("Could not parse JSON from Claude response: %s...", raw_text[:200])
        # Return empty result rather than crashing
        return {"exchange": "unknown", "transactions": []}

    def _insert_transactions(
        self,
        transactions: List[dict],
        user_id: int,
        exchange: str,
        file_import_id: int,
    ) -> dict:
        """Insert extracted transactions into exchange_transactions table.

        Args:
            transactions: list of transaction dicts from Claude
            user_id: owner of the records
            exchange: exchange name (detected by Claude)
            file_import_id: source file_imports.id for reference

        Returns:
            dict with keys: imported, flagged, skipped, errors
        """
        imported = 0
        flagged = 0
        skipped = 0
        errors = 0

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            for index, tx in enumerate(transactions):
                try:
                    # Generate tx_id if not provided by Claude
                    tx_id = tx.get("tx_id") or f"ai_{file_import_id}_{index}"

                    confidence = float(tx.get("confidence", 0.0))
                    needs_review = confidence < CONFIDENCE_THRESHOLD

                    if needs_review:
                        flagged += 1

                    # Build raw_data from the full AI response row
                    raw_data = dict(tx)
                    raw_data["ai_extracted"] = True
                    raw_data["file_import_id"] = file_import_id

                    cur.execute(
                        """INSERT INTO exchange_transactions
                               (user_id, exchange, tx_id, tx_date, tx_type, asset,
                                quantity, price_per_unit, total_value, fee, fee_asset,
                                currency, notes, raw_data, import_batch, source,
                                confidence_score, needs_review)
                           VALUES
                               (%s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s)
                           ON CONFLICT (user_id, exchange, tx_id) DO NOTHING""",
                        (
                            user_id,
                            exchange,
                            tx_id,
                            tx.get("tx_date"),
                            tx.get("tx_type"),
                            tx.get("asset"),
                            tx.get("quantity"),
                            tx.get("price_per_unit"),
                            tx.get("total_value"),
                            tx.get("fee"),
                            tx.get("fee_asset"),
                            tx.get("currency"),
                            tx.get("notes"),
                            json.dumps(raw_data),
                            f"ai_import_{file_import_id}",
                            "ai_agent",
                            confidence,
                            needs_review,
                        ),
                    )

                    if cur.rowcount == 0:
                        skipped += 1
                    else:
                        imported += 1

                except Exception as e:
                    logger.error(
                        "Failed to insert transaction index=%d tx_id=%s: %s",
                        index,
                        tx.get("tx_id", "?"),
                        e,
                    )
                    errors += 1
                    conn.rollback()
                    # Re-get a connection after rollback
                    self.pool.putconn(conn)
                    conn = self.pool.getconn()
                    cur = conn.cursor()
                    continue

            conn.commit()

        finally:
            self.pool.putconn(conn)

        logger.info(
            "Inserted %d transactions (flagged=%d, skipped=%d, errors=%d) for user_id=%d exchange=%s",
            imported,
            flagged,
            skipped,
            errors,
            user_id,
            exchange,
        )

        return {"imported": imported, "flagged": flagged, "skipped": skipped, "errors": errors}

    def _read_file_content(self, filepath: str) -> str:
        """Read and return text content from CSV, XLSX, or PDF file.

        Args:
            filepath: absolute or relative path to the file

        Returns:
            Text content of the file, truncated to 50,000 chars if needed

        Raises:
            ValueError: if file extension is unsupported
            FileNotFoundError: if file does not exist
        """
        MAX_CHARS = 50_000
        path = Path(filepath)
        ext = path.suffix.lower()

        if ext in (".csv", ".txt"):
            # Read directly with BOM handling (utf-8-sig strips BOM if present)
            with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()

        elif ext == ".xlsx":
            try:
                import openpyxl
            except ImportError:
                raise ImportError(
                    "openpyxl is required for XLSX files. Install with: pip install openpyxl"
                )
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            ws = wb.active
            lines = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell) if cell is not None else "" for cell in row]
                lines.append(",".join(cells))
            wb.close()
            content = "\n".join(lines)

        elif ext == ".pdf":
            try:
                import pdfplumber
            except ImportError:
                raise ImportError(
                    "pdfplumber is required for PDF files. Install with: pip install pdfplumber"
                )
            text_parts = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            content = "\n".join(text_parts)

        else:
            raise ValueError(
                f"Unsupported file extension '{ext}'. Supported: .csv, .txt, .xlsx, .pdf"
            )

        # Truncate to avoid hitting Claude context limits
        if len(content) > MAX_CHARS:
            logger.warning(
                "File %s is large (%d chars), truncating to %d chars for Claude API",
                filepath,
                len(content),
                MAX_CHARS,
            )
            content = content[:MAX_CHARS]

        return content

    def _update_import_status(
        self, file_import_id: int, status: str, error_message: Optional[str] = None
    ) -> None:
        """Update file_imports status and optional error message.

        Args:
            file_import_id: ID of the file_imports row
            status: new status value
            error_message: optional error message to store
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE file_imports SET status = %s, error_message = %s WHERE id = %s",
                (status, error_message, file_import_id),
            )
            conn.commit()
        finally:
            self.pool.putconn(conn)
