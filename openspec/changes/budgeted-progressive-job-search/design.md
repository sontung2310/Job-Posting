# Design

## Stage ownership and flow

Keep job-search as coordinator and the three existing stage skills scoped to their
jobs. Add a durable session that references incremental retrieval handoffs and
immutable assessment outcomes, rather than repeatedly preparing an entire growing
input and rescoring it. A cycle acquires at most one batch per available platform
in Seek, LinkedIn, Indeed order. Process each job in that batch before acquiring
the next platform batch. No speculative paid prefetch.

Defaults: batch size 10 raw results, target five eligible jobs, assessment limit
100 unique jobs admitted to condition evaluation, retrieval allowance USD 0.50.
Condition failures count toward 100; duplicates, irrelevant rows and date/data
rejections do not. A fifth qualifier stops assessment immediately; preserve the
unconsumed batch. Eligibility retains existing gate policy and exclusive >75 fit
threshold. Known gate failures cannot qualify; unclear gates carry manual flags.
Provider-filtered date uncertainty is independent of eligibility and visible.

## Time policy

A new acquisition freezes its observation/submission time T and desired interval
[T-lookback, T]. Use Seek dateRange=ceil(lookback/24), without adding queue delay;
24 hours therefore always requests one day. Use LinkedIn's documented 24-hour
preset/filter for 24 hours; verify supported filters for other requested lengths.
Coarse wider periods for other lengths must be explicit limitations, not silent
narrowing. Indeed currently has no supported date request filter: expose this
limitation and validate dates locally. Save the actual request and interval for
every acquisition. Resume never changes historical acquisition intervals.

Exact absolute timestamps outside the acquisition interval are rejected. Dates
with known timezone/observation precision can be represented as possible posting
intervals, never fabricated exact midnight timestamps. Classify confirmed when
that entire interval fits, outside when disjoint, otherwise uncertain. Provider
filtered jobs with uncertain precision may proceed with a visible warning only
when the actual supported lookback filter is recorded and there is no contrary
posting-date evidence. Missing dates without that provenance remain unresolved.
Provider filtering is provenance, not proof of exact time. New reports describe
submission-relative coverage, not one complete fixed run-start interval.

Cached jobs keep their original dates/filter provenance, but must also be checked
against the new session's requested freshness before reuse for a fresh search.
Saved-job scoring may explicitly use historical jobs without claiming freshness.

## Relevance and stopping

Use title and actual role duties, not candidate fit or exact title equality.
Maintain a small configured taxonomy for each query family. Uncertain relevance
proceeds to assessment and cannot count as confidently irrelevant. Seek supports
includeOneInTitle and KeywordRelevance; validate their behavior before relying on
them, since a title-word filter is not an exact-title or semantic guarantee.
LinkedIn does not expose an equivalent verified title constraint in its current
published schema. Preserve user-configured titles/cities; consolidate only
semantically equivalent requests, not distinct role/location coverage.

Proposed defaults pending user feedback: stop a query after two consecutive full
batches each contain fewer than 20% relevant roles. Measure relevance over rows
with sufficient title/duties; insufficient-data rows are unknown. Separately
record duplicate rate and novel relevant yield; duplicates alone do not imply
irrelevance. Short final batches mark exhaustion, not low-relevance evidence.
A source/query stops independently; the platform stops once all its queries are
stopped/exhausted, or a source-level failure prevents further use. Rotate queries
in configured order within each platform. Resume preserves streaks and cursors.
This is a heuristic with possible missed later matches, not proof that all later
results are irrelevant, particularly under newest-first ordering.

## Acquisition capability and cost

Published schemas inspected October 8 expose result caps but no documented
continuation cursor for either configured Apify actor. Seek accepts a search URL,
but this does not prove pagination or state reuse. Implementation must record a
capability finding before incremental paid acquisition. Without verified nonrepeat
continuation, submit one bounded capped run per query, consume its saved response,
and mark the query capped/noncontinuable. Never rerun the prefix with a larger cap.
Do not claim unprocessed dataset pages represent avoided scraping charges.

Before submission reserve the conservative maximum event cost for that batch,
including start and optional events at the account's applicable rates. Defaults
based on the discussed free-plan rates: LinkedIn USD 0.002/result plus 0.00005/start;
Seek USD 0.0025/normal result; salary enrichment off. Verify prices before live
use; no paid-plan upgrade assumed. Allocate sequentially to avoid concurrent
budget overshoot. If enforceable event ceilings cannot be established, block the
paid submission and explain the limitation rather than guarantee a hard cap.
Reconcile actual run charges when available; distinguish estimates/reservations
from actual billing. Unknown submissions retain reservations and cannot be retried.
This is an Apify retrieval budget; evidence embedding and Codex usage are separate.

## Reuse and historical compatibility

Persist raw private responses plus query/filter/cap/cursor identity, actor version,
acquisition times, precision, normalized IDs and consumption position. A compatible
cached batch is consumed before a paid request. Different output directories do
not bypass reuse. Stale or policy-incompatible caches cannot establish new fresh
coverage. Same-source IDs/canonical URLs remove repeats; cross-source merges use
existing conservative identity rules and retain all provenances.

Reuse completed assessments only with matching JD, evidence, resume and scoring
policy fingerprints. Resume failed/unfinished stages, not successful paid calls.
Legacy runs are readable and replayable, never rewritten into the new policy.
A continued session retains budgets/counts; a new budget requires explicit new-run
intent or override. Report IDs/selection validation remain current-report bound.

## External sources

- LinkedIn schema: https://apify.com/curious_coder/linkedin-jobs-scraper/input-schema
- Seek schema: https://apify.com/websift/seek-job-scraper/input-schema
- Actor pricing pages under each actor's /pricing URL.

These establish available inputs, not verified runtime guarantees. No live actors
were submitted during specification work.
