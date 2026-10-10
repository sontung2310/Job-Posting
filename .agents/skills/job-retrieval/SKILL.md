---
name: job-retrieval
description: Discover recent jobs with a configurable lookback, resume saved searches, and return private jobs and coverage without scoring.
---

# Job retrieval

For full-workflow requests, follow job-search’s progressive session actions.
Use bounded acquisition mode below; retain the legacy full-discovery procedure
for explicit retrieval-only requests and existing fixed-window checkpoints.

## Bounded acquisition

Use bridge options `acquisition: true`, `platform`, `title`, `location`,
`maxResults`, `stateRoot` and `cacheRoot` from the coordinator. Pick a durable
run ID scoped to its session and acquisition ID. Read `discovery.py --help` for
CLI options. Process only that configured query; do not exhaust all searches.
New acquisitions use submission-relative freshness windows and supported provider
filters; unfiltered actors are reported explicitly and dates checked locally.
Return jobs, coverage and raw normalized rows for the coordinator’s relevance
review. Reuse saved responses before submitting another actor. Unknown paid
submissions stay blocked for reconciliation; no repeated larger-cap prefix search.
A source cannot claim incremental paid continuation without verified support.
For recoverable failures, follow [workflow recovery](../../../docs/workflow-recovery.md).
Transport `not_submitted` errors permit bounded safe recovery; unknown paid
submissions require reconciliation. Interrupted free Indeed reads can retry
within the runner's bounds. Defer blocked acquisitions through the coordinator
to continue independent sources while preserving reservations and checkpoints.
For a paid acquisition, pass the coordinator’s `--charge-contracts` and
`--charge-limit-usd` to discovery initialization (bridge options `chargeContracts` and `chargeLimitUsd`). The inspected contract must bind
this actor and connector, current prices and the connector schema’s provider-enforced
total USD ceiling; `maxResults` alone is insufficient. The supported REST transport places `maxTotalChargeUsd` in the API query,
not actor input; the bridge invokes the local transport when selected by the contract. Missing or expired contracts block paid submissions; caches and Indeed
remain available. Never invent contract evidence or test a guessed charge argument
with a paid run.

Configured Websift Seek retrieval returns descriptions directly. Historical Bovi
checkpoints read fresh returned job URLs without another actor run.
If the bridge returns `inspections`, inspect each exact URL with available browser/web
tools. Do not search for substitutes. Save the actual full JD and submit it through
`discovery.py accept --request-id ID` as `{"structuredContent":{"url":"URL","description_html":"INSPECTED_TEXT"}}`.
If access fails, submit the same URL with an `error` reason. Never invent or summarize
a full JD. Resume the bridge; unavailable descriptions are excluded. This checkpoint
is source inspection, not permission to edit code or run tests.

## Standalone full discovery

1. Resolve
   the requested lookback from an explicit user override, configuration, then
   default 24 hours. Require positive integer hours. Pick one run ID; a resumed
   run keeps its saved lookback and rejects a conflicting override. Newly initialized
   runs use submission-relative acquisition windows. Only historical checkpoints
   without the rolling policy marker retain the fixed run-start window.
2. Run `./.venv/bin/python scripts/readiness.py --mode discovery`. It validates
   verified evidence eligibility locally. PDF/profile extraction and hybrid
   readiness belong to scoring. Confirm configured connector tools and account
   access without submissions when possible.
   A tool schema does not prove provider access. Use only the configured Indeed
   plugin and LinkedIn/Seek Apify actors; failures do not authorize substitutes.
3. Load `.agents/skills/job-retrieval/scripts/discovery_bridge.js` through `exec_command`, store its returned source
   as `stage1_driver`, then evaluate it in subsequent `functions.exec` calls.
   Configure the bridge with the current absolute checkout and selected run:

   ```javascript
   store("stage1_options", {
     runId: "RUN_ID", cwd: "/absolute/path/to/Job-Search",
     lookbackHours: 48, maxBatches: 1
   });
   await eval(load("stage1_driver"));
   ```

   Omit lookbackHours when there is no explicit override. Inspect progress after
   each bounded batch and resume the same options until every configured search
   has an outcome or supervision_paused is true. Respect returned backoff times.
   The saved supervision deadline defaults to 30 minutes, configured by
   discovery_supervision_minutes. At the deadline, finish the partial handoff and
   stop polling. Extend only after an explicit user request:
   `./.venv/bin/python .agents/skills/job-retrieval/scripts/discovery.py resume --run-id RUN_ID --supervision-minutes MINUTES`,
   then reuse the bridge. The original window and confirmed Actor IDs remain
   unchanged. Helpers own requests, durable responses, Actor IDs,
   pagination, normalization, exact saved-window filtering and duplicates.
4. An unknown paid submission stays blocked until its confirmed run ID is
   reconciled. Use runner `attach --run-id RUN_ID --search-id SEARCH_ID
   --actor-run-id CONFIRMED_ID`, then resume the same bridge. Use runner `--help`
   for argument names. Confirmed reads can resume; never submit an unknown search
   again. An ambiguous rate-limit message is not proof of rejection. Keep
   failures visible and use returned source limitations/caps.
5. Inspect the returned coverage and saved jobs handoff. Verify every configured
   combination is accounted for and every retained job has its full normalized
   description. Preserve effective lookback, original endpoints, checkpoint,
   source outcomes and caps. Existing active/archive applications are excluded.
   Return the saved jobs/coverage paths and numeric wall time, without scores or
   approval candidates. Complete zero jobs succeeds; incomplete coverage remains
   partial. For a full workflow request, return the bounded handoff to job-search for
   its next scoring action, including partial results. Explicit retrieval-only or skill-only
   execution ends here. A source failure does not block scoring retained jobs.

For connector fields, supported date filters and normalized output definitions,
consult [the source reference](references/sources.md) when needed. It is reference material, not a
second procedure. Supported provider filters cover the chosen submission window;
actors without a date input require local validation. Legacy checkpoints retain
their original run-start endpoints.

Development uses saved fixtures. One necessary live acceptance search selects
exactly one platform/title/location, max three results: add `smoke: true`,
`platform`, `title`, `location`, `maxResults: 3` to bridge options. At most one
Apify submission is allowed. Reuse its saved response and confirmed run; another
search after failure requires explicit authorization. Full paid benchmark crawls
are not implementation acceptance.
