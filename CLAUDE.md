# Axiom — Claude Instructions

## SR&ED Evidence Collection (Canada)

This project claims SR&ED tax credits annually. CRA requires **contemporaneous** evidence of technological uncertainty, systematic investigation, and technological advancement — plus time-tracked SR&ED labour. Retroactive documentation is the #1 audit trigger.

**The evidence system lives in [.planning/sred/](.planning/sred/).** Read [.planning/sred/README.md](.planning/sred/README.md) first if you're unfamiliar with it.

### What you must do, without being asked

**1. When a phase completes** (when writing `{N}-VERIFICATION.md`, or when Aaron says a phase is done):
- Open [.planning/sred/PROJECTS.md](.planning/sred/PROJECTS.md) and check the phase's eligibility row.
- If **STRONG** or **LIKELY**: create or update `.planning/phases/{N}-.../{N}-SRED.md` using [.planning/sred/SRED-TEMPLATE.md](.planning/sred/SRED-TEMPLATE.md) as the template. Fill it from the actual contemporaneous artifacts (CONTEXT, RESEARCH, PLAN, commits, VERIFICATION). Link — don't duplicate. See [16-SRED.md](.planning/phases/16-post-quantum-encryption-at-rest/16-SRED.md) as the reference example.
- If **TBD**: assess the phase against the three SR&ED criteria and propose a classification to Aaron. Update `PROJECTS.md` with his answer.
- If **WEAK** or **NO**: do nothing, but note in your response that no SR&ED brief was created and why.

**2. When a new phase is added to the roadmap** (via `/gsd-add-phase`, `/gsd-new-milestone`, etc.):
- Add a row to `PROJECTS.md` with a TBD classification and a one-line uncertainty draft based on the phase's CONTEXT.md. Do this *at phase-creation time*, not later.

**3. At the end of every working session** (when Aaron says "stop", "done for today", "wrap up", "good night", or when you're about to hand off for the day):
- Append a single entry to [.planning/sred/SESSION-LOG.md](.planning/sred/SESSION-LOG.md) using the template in that file. One entry per session. Include: date, session window (morning/afternoon/evening is fine), phases touched, SR&ED-eligible yes/no/partial, one-to-three-sentence summary, key artifacts (commit SHAs, plan files, decisions).
- This is the *backup evidence* for the timesheet. Never skip this. Never edit past entries — add a correction entry below the wrong one if needed.

**4. When Aaron asks to "review my week", "update my timesheet", "log hours", or similar:**
- Read the last 7 days of SESSION-LOG.md and help him reconcile it into [.planning/sred/timesheet.csv](.planning/sred/timesheet.csv). Hours estimates must come from Aaron; you don't invent them. Mark estimates as `EST` in the notes column.

**5. When Aaron mentions a failed approach, a rejected idea, or a pivot during a SR&ED-eligible phase:**
- Capture it in that phase's SRED.md under "Failed attempts / pivots" with today's date and the reason. Failed experiments *prove* uncertainty was real — they're the single most valuable evidence type. Do this even if the phase is still in progress.

### Rules you must follow

- **Never reconstruct retroactively.** If a past date's work isn't in the session log, don't fabricate it. Mark gaps as unknown.
- **Never mix marketing content into SR&ED briefs.** Pitch decks, business plans, and user-facing copy are not SR&ED evidence and don't belong in phase directories.
- **Tie money to phases when it comes up.** If Aaron mentions an invoice, cloud bill, or contractor payment, suggest tagging it with the phase number in the accounting memo line.
- **Preserve failed experiments before deletion.** Before agreeing to `git branch -D` a spike branch or revert a substantial attempt, ask whether it should first be captured in the relevant phase SRED.md.
- **When in doubt about eligibility, ask.** Don't classify a phase STRONG without Aaron's confirmation. It's better to ask than to dilute the claim with weak phases.

### What "eligible" actually means (quick reference)

A phase is SR&ED-eligible if *all three* are true:

1. **Technological uncertainty existed** — a competent professional in the relevant field could not have predicted the outcome from standard practice. "Hard" or "time-consuming" is not enough; the *outcome* had to be unknowable up front.
2. **Systematic investigation was conducted** — hypotheses formed, experiments run, results observed, approach iterated. Not "we tried stuff until it worked."
3. **Technological advancement resulted** — new knowledge generated, even if the project failed commercially or the experiment produced a negative result.

Excluded: routine engineering, bug fixes, UI/UX polish, standard integrations, market research, tool selection without experimentation, documentation, marketing, and anything where the outcome was predictable from day one.

Reference: [CRA — Get ready to calculate your SR&ED claim](https://www.canada.ca/en/revenue-agency/services/scientific-research-experimental-development-tax-incentive-program/sred-claim/get-ready.html)
