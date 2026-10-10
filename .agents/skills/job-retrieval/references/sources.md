# Source reference

Configuration selects enabled sources, title/location combinations and caps.
New bounded acquisitions record submission-relative intervals and actual source
filters. Default lookback is 24 hours; explicit positive integer overrides win.
Legacy full-discovery checkpoints retain their fixed run-start policy.

| Source | Configured adapter | New acquisition date handling |
| --- | --- | --- |
| Indeed | Indeed plugin | No verified posting-date input; validate locally and report limitation. |
| LinkedIn | valig/linkedin-jobs-scraper | Supported past-24-hours filter for 24 hours; do not widen for queue delay. |
| Seek | websift/seek-job-scraper | `dateRange` in days, newest-first; validate the exact requested window locally. |

Inspect the [LinkedIn schema](https://apify.com/valig/linkedin-jobs-scraper/input-schema)
and [Seek schema](https://apify.com/websift/seek-job-scraper/input-schema) when
provider capabilities need verification. Websift returns full JD content through
`content.unEditedContent` / `content.sections`. Bounded requests use `dateRange`,
`sortBy: ListedDate`, `maxResults` and `findSalaries: false`. The optional salary
finder is disabled to avoid extra charges. Historical Bovi checkpoints retain their
original adapter and description-inspection fallback. LinkedIn uses `keywords`,
`location`, `datePosted` and `limit`; longer custom windows use a covering
week/month preset and local filtering; windows beyond a month use an explicit
unfiltered limitation. Neither schema documents a continuation cursor. LinkedIn
exposes `skipJobId`, but exclusions alone do not prove nonrepeat continuation. Caps limit scraped results; dataset read offsets do
not limit already billed scraping. No configured actor substitution is implicit.

Freshness classes distinguish confirmed absolute/interval evidence, uncertain
provider-filtered precision, outside-window dates and unresolved data. Date-only
values never become exact midnight timestamps. Filter provenance may allow
uncertain results to be assessed, with report warnings; it cannot override a
provably old posting date or establish confirmed exact freshness. Indeed has no such filter provenance; Websift day filters still need local
validation of the requested interval. Reused jobs retain original acquisition metadata and must
also satisfy the current fresh-search window.

Normalized jobs retain source/job IDs, URL, employer, position, location, date,
salary, contact and full description, with freshness provenance when available.
Canonical URLs and source IDs remove repeated rows before scoring. Conservative
employer/title/location matching supplements cross-source identity. Raw private
responses remain available for relevance review; public logs contain safe counts.
Existing active/archive application records stay excluded.

Confirmed checkpoints and compatible saved responses are reused before another
search. Unknown paid submissions require reconciliation; larger-cap prefix reruns
are prohibited. Reports expose capped/noncontinuable queries, exclusions,
relevance judgments and incomplete coverage. Post-retrieval deduplication saves
assessment work, not result charges already incurred.

Old checkpoints retain their saved actor/input contracts. Switching actors separates
new acquisition caches and invalidates old paid-charge contracts. Reconnect the
Apify MCP server after changing its tool list; no fallback to the old actor is
authorized for a new run. Result caps do not prove total charge ceilings.

Valig `postedDate` is calendar precision even when formatted as midnight ISO.
Do not call it an exact posting instant. Keep uncertain dates visible in coverage.
