# Workflow recovery

Use this procedure when a workflow interaction fails. Preserve the current
session, frozen inputs, private packets, reservations and checkpoints.
Corrections change working submissions, never verified career facts or source
resumes. Recovery does not authorize code edits, tests, application writes or
additional paid retries.

## Classify and recover

- **Invalid submission:** read the saved diagnostics and accepted templates.
  Correct references, required fields or resume-line IDs using existing packets.
  Make at most two corrected submissions per job after its first failure. Use
  allowed evidence IDs; inspect their excerpts. Unsupported claims get no credit.
  Inspect summary/results even when the command exits successfully.
- **Transient read or busy operation:** respect returned backoff and locks.
  Allow at most two retries of a read known to be safe, unless the runner has
  already consumed its retry allowance. Reuse confirmed Actor IDs and evidence
  retrieval; do not overlap an active operation.
- **Not submitted:** a structured transport response confirming no paid POST
  occurred permits safe preflight recovery within the same read retry bounds.
  Missing credentials or changed pricing are dependencies to resolve, not
  permission to invent credentials, refresh an active session's charge policy,
  or submit outside its allowance.
- **Unknown paid submission:** retain its reservation and original checkpoint.
  Reconcile the confirmed Actor ID before another submission for that acquisition.
  If no ID is known, keep the operation blocked and reconcile the original
  transport checkpoint; never invent an ID or relaunch the request.
  Unknown embedding operations retain their approval requirement. Never use a
  new directory or run to bypass a pending paid operation.
- **Integrity failure:** changed verified evidence, frozen scoring decisions,
  resumes or finalized provenance stop affected work. Preserve historical
  records; report the specific mismatch. Never disable validation.

## Isolate unresolved work

After bounded recovery fails, defer a job or acquisition with a safe summary and
its actual checkpoint path:

```bash
./.venv/bin/python .agents/skills/job-search/scripts/progressive.py defer --run SESSION --target assessment --failure-kind validation_input --reason "Invalid submission remains unresolved" --checkpoint PRIVATE_RUN
./.venv/bin/python .agents/skills/job-search/scripts/progressive.py defer --run SESSION --target acquisition --failure-kind unknown_submission --reason "Paid submission needs reconciliation" --checkpoint CHECKPOINT
```

Use `dependency_unavailable` or `source_unavailable` for those failure kinds.
Save the returned deferred ID, then call `next --run SESSION`. The coordinator
preserves the original item and reservation; unresolved paid work blocks its
affected source while independent allowed work proceeds. Failed submissions earn
no assessment or eligibility credit.

When the blocker resolves, restore the exact saved item:

```bash
./.venv/bin/python .agents/skills/job-search/scripts/progressive.py resume --run SESSION --deferred-id ID
```

Resume the original checkpoint. Restoration does not authorize resubmitting an
unknown paid request. If all remaining work is blocked, publish
`progress --run SESSION` with unresolved counts and concrete resume points.
Never spin through blocked items or request selection from an incomplete report.

## Completion and coverage

After an explicitly authorized code repair, an unpublished session can use the
supported migration command. Read OLD from its saved scoring policy:

```bash
./.venv/bin/python .agents/skills/job-search/scripts/progressive.py migrate-code --run SESSION --expected-code-fingerprint OLD --reason "Authorized recovery implementation"
```

Migration verifies every admitted outcome against current evidence and scoring
and requires unchanged results before updating the code fingerprint. It preserves
counts, reservations and queues. If verification fails, retain the checkpoint
and report the mismatch; never reset the fingerprint manually. Published reports
remain immutable. This command is for authorized repairs, not ordinary discovery.

Report five eligible jobs, the paid retrieval allowance, or verified exhaustion
as normal stopping reasons. Preserve optional limits already saved in sessions.
Provider caps, low relevance, unavailable sources and supervision deadlines
describe incomplete coverage. They cannot prove that all jobs in the lookback
window have been found. Actual exhaustion requires verified provider completion
or supported nonrepeat continuation; repeated capped prefix scrapes are unsafe.

At supervision expiry, save progress and continue independent supported work.
Extending a deadline follows the retrieval skill's explicit authorization rule.
Deferred items remain visible and nonselectable until resolved. Reservations are
conservative ceilings; show actual billing as unavailable when it is unknown.
