# Phase {N} — SR&ED Brief

**Phase:** {N} — {phase name}
**Fiscal year:** {YYYY}
**Eligibility:** STRONG | LIKELY | WEAK | NO
**Status:** DRAFT | READY FOR FILING | FILED
**Last updated:** {YYYY-MM-DD}

> **Instructions for Claude:** Fill this at phase completion using contemporaneous evidence from the phase directory. Link to — don't duplicate — existing artifacts (`CONTEXT.md`, `RESEARCH.md`, `PLAN.md`, `VERIFICATION.md`, git commits). If a section can't be filled honestly, say "not documented" rather than inventing. Never reconstruct months later.

---

## 1. Project summary (T661 Line 240, ~350 words)

One to three paragraphs describing what the project was, what technical problem it addressed, and what was delivered. Plain English but technically precise. This is the narrative a CRA reviewer reads first.

---

## 2. Technological uncertainty (T661 Line 242)

**What was unknown going in?**

- {Specific uncertainty #1 — what couldn't be predicted from standard practice, and why}
- {Specific uncertainty #2}
- {Specific uncertainty #3}

**Why couldn't a competent professional have solved this with existing knowledge?**

Explain what "standard practice" would have been and why it was insufficient. Link to the specific CONTEXT.md or RESEARCH.md section that flagged the uncertainty *before* work began.

- [Phase CONTEXT.md — Decisions D-XX](../phases/{N}-.../{N}-CONTEXT.md)
- [Phase RESEARCH.md — Open questions](../phases/{N}-.../{N}-RESEARCH.md)

---

## 3. Systematic investigation (T661 Line 244)

**Hypotheses tested:**

1. {Hypothesis 1} — evidence: {commit SHA / PLAN.md section / test file}
2. {Hypothesis 2} — evidence: ...

**Experimental procedure:**

Describe the sequence: what was tried first, what was measured, what was observed, how the next iteration was chosen. Tie to PLAN.md task breakdown and git history.

- [PLAN.md — Task breakdown](../phases/{N}-.../{N}-01-PLAN.md)
- Git commits: `git log --oneline --grep="phase {N}"`

**Failed attempts / pivots:**

Critically important — CRA *wants* to see failures. Each one proves the uncertainty was real.

- {Approach X tried on YYYY-MM-DD — failed because Z — pivoted to W} — commit: `abc1234`
- {...}

---

## 4. Technological advancement (T661 Line 246)

**New knowledge generated:**

What does the team now know that it didn't before? Even negative results count ("approach X does not work for workload Y at scale Z").

- {Knowledge point 1}
- {Knowledge point 2}

**How this advances beyond the baseline:**

Baseline = standard practice at the start of the project. What's now possible that wasn't?

- [VERIFICATION.md — Measured outcomes](../phases/{N}-.../{N}-VERIFICATION.md)
- [VALIDATION.md — Benchmark deltas](../phases/{N}-.../{N}-VALIDATION.md)

---

## 5. Supporting evidence inventory

Contemporaneous artifacts, in the order a CRA reviewer would request them:

| Evidence | Location | Date range |
|---|---|---|
| Phase CONTEXT (uncertainty framing) | `{N}-CONTEXT.md` | {date gathered} |
| Research notes | `{N}-RESEARCH.md` | {date range} |
| Execution plans | `{N}-NN-PLAN.md` | {date range} |
| Source control history | `git log --grep="phase {N}"` | {date range} |
| Test results / benchmarks | `{N}-VERIFICATION.md`, test output logs | {date range} |
| Decisions and discussion log | `{N}-DISCUSSION-LOG.md` | {date range} |
| Commit-level atomic work units | GitHub / local git | {date range} |

---

## 6. Labour (populated from timesheet.csv at filing)

| Person | Hours | Role | Notes |
|---|---|---|---|
| {...} | {...} | {...} | {...} |

Query: `grep ",{N}," ../sred/timesheet.csv | awk -F, '{sum+=$4} END {print sum}'`

---

## 7. Other expenditures (populated at filing)

- Cloud infrastructure attributable to this phase: {$X}
- Contractor costs: {$X}
- Materials / licensed software: {$X}

Invoices and receipts tagged with phase {N} in memo line.

---

## 8. Confidence check (self-review before filing)

- [ ] Uncertainty is specific (not "it was hard") and was flagged *before* work began
- [ ] Systematic investigation evidence is contemporaneous (dated commits, PLAN.md timestamps)
- [ ] At least one failed attempt documented
- [ ] Advancement is measurable (benchmark, correctness result, or capability delta)
- [ ] Labour hours come from contemporaneous timesheet entries, not reconstruction
- [ ] No marketing/pitch content mixed in
