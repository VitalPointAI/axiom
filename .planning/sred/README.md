# SR&ED Evidence Collection

Contemporaneous, dated, project-tagged evidence for Axiom's CRA SR&ED claim (Canada).

## Why this exists

CRA requires three things for every SR&ED project:

1. **Technological uncertainty** — a competent professional couldn't have predicted the outcome from standard practice
2. **Systematic investigation** — hypothesis → experiment → result → iteration
3. **Technological advancement** — new knowledge generated (even from failed attempts)

Plus **time tracking** of SR&ED labour, logged during the year — *not* reconstructed at filing time. Retroactive documentation is the #1 audit trigger.

Reference: [CRA — Get ready to calculate your SR&ED claim](https://www.canada.ca/en/revenue-agency/services/scientific-research-experimental-development-tax-incentive-program/sred-claim/get-ready.html)

## What's in this folder

| File | Purpose | Update cadence |
|---|---|---|
| [PROJECTS.md](PROJECTS.md) | SR&ED project register — which phases are eligible, one-paragraph technical narratives | On every new phase; at phase completion |
| [SRED-TEMPLATE.md](SRED-TEMPLATE.md) | Per-phase brief template — copy into each eligible phase as `{N}-SRED.md` | Once per eligible phase |
| [timesheet.csv](timesheet.csv) | Weekly SR&ED labour log (date, person, phase, hours, notes) | Weekly (or end of session) |
| [SESSION-LOG.md](SESSION-LOG.md) | Append-only log of Claude-assisted work sessions — contemporaneous trail for backfilling timesheet | End of every working session |

## How it stays up to date

The workflow is driven by instructions in the project's [CLAUDE.md](../../CLAUDE.md). Specifically:

1. **When any phase completes** (VERIFICATION.md written), Claude checks `PROJECTS.md` to see if it's listed as SR&ED-eligible. If yes → creates/updates the phase's `SRED.md`. If undetermined → asks Aaron to classify.
2. **When a new phase is created**, Claude evaluates eligibility and adds a row to `PROJECTS.md`.
3. **At session end** (or when Aaron says "stop" / "done for today"), Claude appends a `SESSION-LOG.md` entry with date, phases touched, and a one-line summary.
4. **Weekly** — Aaron should review `SESSION-LOG.md` and reconcile it into `timesheet.csv` with actual hours. Claude can help with this on request (`review my week` or similar).

## Rules

- **Never reconstruct retroactively.** If you don't know the actual hours for a past day, mark them `EST` in the notes column and move on. CRA prefers "honest estimate with contemporaneous trail" over "fabricated precision."
- **Preserve failed experiments.** Before deleting a spike branch or reverting an approach, drop a dated note in the phase `SRED.md`. Failures *prove* uncertainty was real.
- **Tie money to phases.** Invoices, contractor payments, and cloud bills should reference the phase number in the memo line. This lets salary + overhead + materials roll up cleanly per project at filing time.
- **Separate marketing from technical evidence.** Pitch decks and business plans are *not* SR&ED evidence. Keep them out of phase directories.

## What to do at tax-filing time

1. Open `PROJECTS.md`, pick the phases worth claiming for the fiscal year
2. For each, read the phase's `SRED.md` — it already has the T661 Part 2 narrative
3. Sum `timesheet.csv` rows by phase to get SR&ED labour hours
4. Multiply by hourly cost to get T661 Part 3 salary expenditures
5. Hand everything to your SR&ED consultant or fill T661 yourself
