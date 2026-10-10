---
name: job-scoring
description: Assess saved jobs against verified career evidence and every current resume, then end at a ranked scoring report for human selection. No detailed suggestions, new source searches or destination writes.
---

# Job scoring

When invoked by a progressive job-search session, assess only its returned job
input and return the finalized run/outcome to the coordinator. The coordinator
presents the aggregate report and waits for selection at its stop point. A
standalone saved-job scoring request still ends at its own ranked report.

1. Accept the saved jobs/coverage handoff; retain partial or unknown discovery coverage. Prepare:

   ```bash
   ./.venv/bin/python .agents/skills/job-scoring/scripts/assessment.py prepare --input HANDOFF --output PRIVATE_RUN
   ```

   The CLI returns a run_handle, counts and private response paths. Read jobs in
   bounded pages:

   ```bash
   ./.venv/bin/python .agents/skills/job-scoring/scripts/assessment.py inspect --run HANDLE --offset 0 --limit 1
   ```

   Read shared inputs once per unchanged run:

   ```bash
   ./.venv/bin/python .agents/skills/job-scoring/scripts/assessment.py inspect --run HANDLE --shared
   ```

   Subsequent pages reference this shared handle and compact discovery counts.
   Each job page retains its full JD, numbered units, working templates and
   inspectable evidence. Follow next_offset until every original job is accounted
   for. Reuse validated outcomes on resumed runs.
   Reuse accepted condition/classification templates returned by inspection;
   source completion and retries preserve accepted decisions.
   Scoring readiness checks local inputs and reuses valid profile/PDF text.
   Hybrid index setup starts only after a job passes the condition gates. Nonempty runs need at least two
   resumes. Empty handoffs finalize without scoring dependencies and preserve
   completed, partial or unknown discovery coverage.
   No source credentials or new Indeed/Apify searches are needed. Save a working
   copy of the returned decision template; helpers manage internal filenames and
   fingerprints. For changed finalized inputs, use a new scoring run.
2. Inspect each complete JD and verified profile. Complete each template's
   condition and classifications. Work rights and explicitly required degrees
   are gates: known mismatch fails before retrieval/scores; ambiguity proceeds
   with original wording flagged for manual review. Skills, licences and
   certifications affect fit rather than independently gate jobs. Failed jobs
   need no scoring classifications. Eligible jobs classify every numbered unit
   as Skills, Experience, Domain or ignore, with priority 3 (essential), 2
   (standard) or 1 (preferred), and a reason. Preserve compound scope and seniority.
   Benefits, education-only clauses and standalone keywords use ignore and
   earn no points.
   Use [the scoring reference](references/scoring.md) for definitions when needed.
3. Submit the decisions using the returned run handle:

   ```bash
   ./.venv/bin/python .agents/skills/job-scoring/scripts/assessment.py requirements --run HANDLE --input DECISIONS
   ```

   Submit at most three jobs per interaction, preferably one. Wrap the selected
   templates in {"jobs": [...]}. Read compact progress, then inspect the same
   page for packets and judgments_template. The helper saves
   accepted conditions, freezes requirements and retrieves evidence for every
   eligible requirement in original wording. For linked external evidence,
   requirements returns `awaiting_sources` with the exact URLs needing inspection.
   Read those pages, then resubmit the same decisions with the complete inspected
   text map; the helper reuses its saved retrieval without new embeddings.
   Supply `--linked-sources SOURCE_TEXT_MAP` keyed
   by exact source URL; this verifies evidence, not new job discovery. Unavailable
   sources remain explicit failures. Interrupted/failed hybrid work leaves a
   durable pending marker; stop that paid operation and report the failure. Retry
   only after explicit user approval using --authorize-paid-retry on the affected
   prepare or requirements command. Keep the same run/cache; changing paths
   cannot bypass a pending paid operation. A busy operation is still active in
   another run: resume after it finishes; paid-retry approval cannot override its lock. Reuse accepted work for local repairs;
   preserve inspected excerpts and document-specific provenance hashes.
4. Inspect verified claims, supporting sources and exact resume lines in each
   packet. Set judgment category to AI Agent, Computer Vision or Hybrid; this
   describes the job and differs from requirement categories. Complete every
   requirement's direct/strong_transfer/partial_transfer/missing/unknown strength,
   reason, citations and each resume's supporting line IDs. Apply
   [the scoring reference](references/scoring.md) before judging transfer strength
   or evidence gaps. Explain the capability that transfers and its remaining gap.
   An undocumented capability is unknown; a confirmed limitation is missing.
   Resume omissions affect resume coverage independently of candidate capability.
   Choose citations from the packet's allowed evidence catalog using
   `evidence_id`. Full-note context does not make every heading an allowed
   citation. Inspect the exact catalog excerpt and source before crediting it.
   Submit score judgments first:

   ```bash
   ./.venv/bin/python .agents/skills/job-scoring/scripts/assessment.py judgments --run HANDLE --input JUDGMENTS
   ```

   Both qualified and below-threshold jobs finalize immediately after validated
   scoring. Detailed suggestions belong to job-suggestions after human selection;
   do not submit suggestions through this scoring interface.

   An `evidence_review` outcome has a provisional range crossing the qualification
   threshold. Ask concise questions about the returned unknown requirements and
   resubmit judgments against the same packet when clarified. If career evidence
   changes, prepare a new scoring run. In a progressive search, return this outcome
   to `progressive.py assessed`; the coordinator defers it and continues other jobs.
   It remains unresolved and does not count toward the eligible target.

   Read the compact summary and inspect pages for validated outcomes. An
   in_progress summary means other original jobs still need review; continue
   through the remaining pages. Helpers validate independent frozen inputs,
   sources and lines, calculate fit and every resume's coverage, save outcomes
   and own condition/scoring/suggestion logs. Do not duplicate those logs or call
   a separate calculator/finalizer. Repair missing/invalid jobs through the same
   interactions within the paid-retry boundary above; successful finalized
   judgments require a new run for revisions.
   For invalid submission diagnostics, follow [workflow recovery](../../../docs/workflow-recovery.md).
   Repair the listed references and line IDs using the same saved packet, at
   most twice. If evidence does not support a claim, mark it missing rather
   than inventing or substituting a citation. Progressive searches defer an
   unresolved job through the coordinator and continue other work.
5. Account for every original job, including distinct jobs with identical
   descriptions and gate failures. Continue through unresolved jobs; batch boundaries and saved checkpoints are intermediate results.
   Helpers save private report.json/report.md with explicit remaining work.
   Incomplete reports are NONSELECTABLE; resume until all jobs have resolved
   outcomes. Incomplete reports remain visible and nonselectable. Final report numbers and
   identity are immutable. Never request selection from an incomplete report. Present every qualifier
   using its stable candidate number in descending fit order with identity,
   location, source/date/URL, advertised salary/contact when present, three-key
   match JSON, every resume's coverage, a brief evidence-match explanation and original manual-review wording. Keep full evidence tables private. Present discovery
   coverage separately from assessment outcome counts, concrete failures, remaining
   jobs, the resume point and actual scoped wall time. Partial coverage never
   becomes a successful empty run. Native scheduled results include each scored
   JD's fit and a brief reason; unavailable native usage/cost stay null. CLI runs
   preserve their separate completed-turn finalization.
6. Display the ranked report and its report ID. With qualifiers, wait for the
   user's current-report selection; state that no application records were written.
   Complete coverage with no qualifiers needs no approval request. Scoring ends
   at this report. AGENTS.md owns routing after selection; this skill performs
   neither detailed suggestions nor destination preparation.

Done when every original job is accounted for and the ranked scoring report is
presented, or a concrete blocker is reported with saved progress and a resume
point. Checkpoints and batch boundaries are intermediate results. Use generated
templates and helper --help as the current input contract.
