---
status: partial
phase: 15-account-block-index-integer-encoding
source: [15-VERIFICATION.md]
started: 2026-04-11T20:53:00Z
updated: 2026-04-11T20:53:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Wallet lookup end-to-end timing (INT-08)
expected: Sync a NEAR wallet via the v2 segment index path and confirm it completes in under 2 minutes
result: [pending]

### 2. Storage size under 250 GB (Phase Goal)
expected: pg_total_relation_size('account_block_index_v2') + pg_total_relation_size('account_dictionary') < 250 GB after full migration
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
