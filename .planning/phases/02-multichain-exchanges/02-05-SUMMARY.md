---
phase: 02-multichain-exchanges
plan: 05
subsystem: ai, ingestion
tags: [anthropic, claude-api, file-ingestion, confidence-scoring, csv, xlsx, pdf, psycopg2]

# Dependency graph
requires:
  - phase: 02-01
    provides: exchange_transactions table schema with confidence_score and needs_review columns

provides:
  - AIFileAgent class in indexers/ai_file_agent.py
  - Claude API-based extraction of transactions from CSV, XLSX, PDF exchange exports
  - Confidence scoring (0.0-1.0) with automatic needs_review flagging below 0.8 threshold
  - 17 unit tests with full mock coverage (zero real API/DB calls)

affects:
  - 02-06 (smart routing: unknown formats routed to AIFileAgent)
  - Phase 3 transaction classification (needs_review flag for human review queue)

# Tech tracking
tech-stack:
  added: [anthropic SDK (lazy import), openpyxl (XLSX), pdfplumber (PDF)]
  patterns:
    - Lazy Anthropic client init via @property to avoid import at module load
    - CONFIDENCE_THRESHOLD=0.8 as module constant for easy tuning
    - Fallback JSON extraction via regex when Claude wraps JSON in markdown
    - ai_{file_import_id}_{index} deterministic tx_id generation for dedup

key-files:
  created:
    - indexers/ai_file_agent.py
    - tests/test_ai_file_agent.py
  modified: []

key-decisions:
  - "Lazy Anthropic client init: import anthropic inside @property avoids startup failure if SDK not installed"
  - "CONFIDENCE_THRESHOLD=0.8 as module constant: easy to tune and importable by routing layer"
  - "Regex fallback for JSON extraction: Claude sometimes wraps response in markdown code blocks"
  - "ai_{file_import_id}_{index} for missing tx_id: deterministic and enables ON CONFLICT dedup"
  - "source='ai_agent' for all AI-extracted transactions: distinguishes from CSV parser and API connector records"
  - "50k char truncation for large files: manages Claude context window without chunking complexity"

patterns-established:
  - "Lazy client init via @property: pattern for optional heavy dependencies (anthropic SDK)"
  - "Confidence-gated needs_review: numeric score controls boolean flag at insertion time"
  - "Robust JSON parsing: try direct parse, fall back to regex extraction, return empty on failure"

requirements-completed: [DATA-05]

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 2 Plan 05: AI File Ingestion Agent Summary

**AIFileAgent class using Claude claude-sonnet-4-20250514 to extract transactions from any exchange export (CSV/XLSX/PDF) with confidence scoring, needs_review flagging at 0.8 threshold, and 17 mocked unit tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-12T18:50:16Z
- **Completed:** 2026-03-12T18:53:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- AIFileAgent class with Claude API integration handles any unknown exchange export format
- Confidence scoring (0.0-1.0) automatically flags transactions below 0.8 as needs_review=True
- File reading supports CSV (utf-8-sig BOM), XLSX (openpyxl row-to-text), PDF (pdfplumber), with 50k char truncation
- 16 tests passing + 1 skipped (openpyxl not installed in CI environment, properly handled with skipTest)
- Zero real API calls in tests — all Anthropic client and pool interactions fully mocked

## Task Commits

Each task was committed atomically:

1. **Task 1: Create AI file ingestion agent with Claude API** - `d0ed052` (feat)
2. **Task 2: Create unit tests for AI file agent** - `b231f96` (test)

## Files Created/Modified

- `indexers/ai_file_agent.py` - AIFileAgent class: process_file(), _extract_transactions() (Claude API), _insert_transactions() (psycopg2 with ON CONFLICT), _read_file_content() (CSV/XLSX/PDF), _parse_json_response() (with regex fallback)
- `tests/test_ai_file_agent.py` - 17 unit tests covering response parsing, confidence flagging, CSV/XLSX reading, tx_id generation, source field, invalid JSON handling

## Decisions Made

- Used lazy `@property` init for Anthropic client — avoids import error at module load if SDK not installed; client only instantiated when process_file() is actually called
- CONFIDENCE_THRESHOLD=0.8 as importable module constant — smart routing layer (02-06) can import and use the same threshold
- Regex fallback JSON extraction — Claude occasionally wraps JSON in markdown ```json``` blocks; regex handles this without crashing
- Deterministic `ai_{file_import_id}_{index}` for missing tx_id — enables ON CONFLICT dedup on re-import without requiring Claude to generate consistent IDs
- 50k char truncation instead of chunking — simpler implementation; chunking can be added later if needed for very large files

## Deviations from Plan

None — plan executed exactly as written. All 7 specified test scenarios implemented (extract parsing, confidence flagging, CSV reading, XLSX reading, tx_id generation, source field, invalid JSON handling), plus additional edge case tests (BOM stripping, file truncation, API key missing, model name verification).

## Issues Encountered

None. openpyxl not installed in environment but test correctly uses `self.skipTest()` as the plan specified.

## User Setup Required

None — no external service configuration required for the agent code itself. ANTHROPIC_API_KEY must be set at runtime (the agent raises EnvironmentError with clear message if absent).

## Next Phase Readiness

- AIFileAgent is ready for integration into smart routing (Plan 02-06)
- Smart router: known formats → ExchangeParser implementations, unknown formats → AIFileAgent.process_file()
- needs_review=True records will surface in Phase 3 human review queue for transaction classification
- CONFIDENCE_THRESHOLD can be imported from indexers.ai_file_agent for consistent routing decisions

---
*Phase: 02-multichain-exchanges*
*Completed: 2026-03-12*
