---
name: job-search
description: Run this project's full job-search workflow for fresh jobs, through the ranked scoring report and human selection. Use for end-to-end job-search requests, not workflow discussion or retrieval-only/scoring-only requests.
---

# Job search

1. Read [AGENTS.md](../../../AGENTS.md), configuration and career evidence rules.
   Resolve the requested lookback, otherwise configuration, otherwise 24 hours.
   Start or resume one private progressive session with
   `.agents/skills/job-search/scripts/progressive.py`; use its `--help` for options.
   Before a new session, refresh the private charge contracts using the procedure
   below. Use `init --run SESSION --config config/search_targets.yaml --charge-contracts .state/apify-charge-contracts.json`; it resolves
   enabled platforms and configured title/location queries. Pass an explicit user
   lookback as `--lookback-hours`; resumed overrides must match saved policy.
   Configuration overrides belong in `progressive_search`; validate the resolved
   session policy. Defaults are five eligible jobs, batches of ten and USD 0.50
   Apify retrieval. Assessment limits are optional; resumed sessions retain saved
   limits. Explicit overrides must be visible.
2. Call `next --run SESSION`. For an acquire action, use
   [job-retrieval](../job-retrieval/SKILL.md) in acquisition mode with exactly the
   returned source, title, location and cap. Use the returned acquisition ID under
   the session; preserve the returned cache root. Never prefetch another paid
   batch while this batch remains unassessed. Seek, LinkedIn and Indeed rotate;
   unavailable sources are accounted for instead of blocking the others.
3. Inspect the acquisition coverage and its `raw_jobs_path`. Supply relevance
   judgments for the raw batch using title and duties: relevant, irrelevant or
   uncertain, with reasons. Relevance means belonging to the requested role
   family, not candidate fit. Incidental AI mentions or AI-assisted coding do not
   establish AI engineering duties. Preserve ambiguous adjacent roles for scoring.
   Use the coordinator's `ingest` contract to pass the saved jobs, coverage and
   judgments; do not fabricate provider coverage or continuation capabilities.
4. For an assess action with `reused: true`, import the returned finalized
   assessment run with `assessed` without rescoring. Otherwise use
   [job-scoring](../job-scoring/SKILL.md) on the returned singleton input and run. Finish the condition/evidence/score
   review,
   then import its finalized outcome with `assessed`. Reuse matching finalized
   runs; do not rewrite historical scores. Call `next` again after each outcome.
   Known condition failures count toward the assessment limit. Duplicates and
   retrieval rejections do not. Exactly 75 does not qualify.
   If an interaction fails, follow [workflow recovery](../../../docs/workflow-recovery.md).
   Correct invalid submissions using saved packets, then defer unresolved jobs
   after bounded correction and call `next` to process independent work.
   Never count an invalid assessment as below threshold or as an eligible job.
   Return provisional `evidence_review` outcomes through `assessed` as well. It
   saves a deferral with the score range and unknown IDs; continue independent
   jobs and report the clarification needed. Changed scoring weights or credits
   require a new session using saved acquisition results, preserving old scores.
For a `reconcile` action, inspect and reconcile the referenced original checkpoint
without resubmitting its actor, then call `next` again.
For a `blocked` action, call `progress --run SESSION` and report its unresolved
items and resume points. Restore a deferred item only after its blocker resolves;
do not loop on an unchanged blocker or treat it as completed coverage.

5. For a report action, call `report --run SESSION` and present the returned
   report with stable candidate numbers. Include costs, freshness uncertainty,
   source/query stopping reasons and unsearched coverage. These are first found
   qualifiers, not exhaustive best-five matches. Save unused jobs for continuation.
   Use `progress --run SESSION` for aggregate checkpoints. Deferred jobs or
   acquisitions keep the report nonselectable. Resume them with the supported
   `resume` command when the blocking condition resolves. A provider cap,
   unavailable source or low-relevance query stop is incomplete coverage,
   not proof that no more fresh jobs exist.
6. Only when the returned report has `selectable: true`, wait for explicit
   selection from that report. For nonselectable progress, continue supported
   recovery or report concrete unresolved blockers. Follow AGENTS.md routing to
   selected-job suggestions and enabled destination preparation. No suggestions,
   application records or cover letters are produced during this search loop.

Stop low-relevance queries dynamically, not at a fixed result position. Default
policy is two consecutive full evaluable batches below 20% relevance; uncertainty
and duplicate rate are separate. Stop a platform only after its queries are all
stopped/exhausted or a source-level blocker. Current actors have no verified
nonrepeat continuation: a capped query may end after one bounded acquisition.
Dataset pagination cannot justify additional paid scraping or claimed savings.

Resume preserves counts, reservations, consumed jobs and unresolved paid requests.
A stopped report remains immutable; an explicit continuation must retain prior
state and use the coordinator's supported continuation contract, not reset limits
silently. If continuation is unsupported, explain it and preserve the queue.

Paid acquisition uses the capped Apify REST transport. Before initializing a new
session, refresh the private charge contracts with the read-only inspector:

```bash
./.venv/bin/python .agents/skills/job-retrieval/scripts/apify_transport.py inspect --output .state/apify-charge-contracts.json
```

On first setup, supply `--seek-run ID --linkedin-run ID` using confirmed historical
Actor runs. The inspector checks current pay-per-event pricing and that platform
usage is paid by the developer; unsupported pricing remains blocked. Later refreshes
reuse the saved billing run IDs. Pass `--charge-contracts .state/apify-charge-contracts.json`
to progressive initialization. Contracts expire after 24 hours. Do not replace a
running session's contracts or reset its reservations to bypass a blocker.

The bridge submits once through `apify_transport.py`, with `maxTotalChargeUsd` in
the REST query rather than actor input. It rechecks pricing before submission,
reserves all possible result events (including the Seek salary-finder event), and limits memory to
512 MB so the LinkedIn start fee has one billable event. Unknown submissions remain
blocked for reconciliation. Existing cache and free Indeed queries remain usable
without a paid contract. No new paid smoke tests are part of normal execution.
When `next` returns `charge_contracts` and `charge_limit_usd`, pass both to discovery
initialization. The budget covers Apify retrieval; embeddings and Codex usage are
separate. Reservations are conservative ceilings, not reported actual billing.
