# Verification and acceptance

## Saved-run findings verified during specification

Private input: .state/stage1/20261008-fresh-24h/checkpoint.json, read-only.
No actor submissions or paid searches were made. Source identity used each raw
row's id, falling back to its source URL. These totals were asserted by a local
Python replay inspection on October 8, 2026:

| Source | Raw entries | Unique within source | Repeated entries |
| --- | ---: | ---: | ---: |
| LinkedIn | 410 | 228 | 182 |
| Seek | 282 | 186 | 96 |
| Total | 692 | 414 | 278 |

414 is a sum of within-source unique counts, not a cross-source unique total.
All 24 saved Seek task filters requested dateRange=2. Seek raw dates include
86 October 6 entries, 148 October 7 entries and 48 October 8 entries. The original
fixed window started October 7 at 04:19:53 UTC. The 86 October 6 rows therefore
cannot satisfy it. LinkedIn's 410 rows have calendar-only October 7/8 postedAt
values: 272 and 138 respectively, not exact timestamp proof.

Observed query examples: LinkedIn AI Engineer returned Integration Consultant
and SAP Full Stack Developer; Seek AI Engineer returned Modern Workplace Engineer
and CX Analyst. These demonstrate broad search behavior, not a complete labelled
relevance benchmark. Duties must be inspected before making final relevance labels.
The old filtered handoff contained 90 Seek jobs. Its scored outcomes were 78 below
threshold and 12 condition failures; zero qualifiers. This is historical behavior,
not an acceptance target for the new policy or proof of accurate scoring.

At the user-supplied rates the raw result estimate is USD 1.525 before start/other
events; this is not an actual bill. Replays cannot prove that new provider filters
would return a particular count or save a particular amount. Savings require
avoided submissions/charged events, not merely fewer retained rows.

## Required implementation success criteria

Use existing discovery/assessment public CLI interfaces and the coordinator's
public session contract with deterministic mocked connectors. Assert observable
behavior rather than private helper structure. The implementation results and
provider limitations are recorded below.

1. **Dates:** a delayed 24-hour Seek acquisition submits dateRange=1; LinkedIn
   submits its verified past-24-hours filter. Queue/resume delay does not widen it.
   48/72-hour overrides use supported covering filters and report coarse limits.
   Exact old/future timestamps are excluded, date-only values remain explicitly
   uncertain unless interval evidence proves freshness, and unfiltered Indeed
   does not inherit another platform's filter provenance.
2. **Replay precision:** all 410 saved LinkedIn calendar-only rows remain marked
   with original precision, never fabricated exact dates or silently all labelled
   confirmed. Replaying old two-day filters cannot claim they were new 24-hour
   provider requests. The 86 October 6 Seek entries cannot enter the original
   interval's confirmed set. Keep raw originals and historical reports unchanged.
3. **Relevance benchmark:** privately hand-label at least 30 unique saved jobs,
   including related AI titles, unrelated titles with incidental AI mentions and
   ambiguous duties. Every clearly unrelated labelled fixture is rejected from
   scoring; every clearly relevant labelled fixture is retained. Ambiguity is
   visible, not forced into irrelevance. Record adjudication reasons; title alone
   is insufficient for ambiguous examples.
4. **Order and limits:** mocked trace demonstrates acquire Seek, assess its batch,
   acquire LinkedIn, assess, acquire Indeed, assess. Fifth eligible result stops
   immediately; unused batch remains saved. The 100th unique gate assessment also
   stops, including gate failures. Duplicate/rejected rows do not count toward 100.
   Scores of exactly 75 do not qualify. Unavailable sources are skipped visibly.
5. **Dynamic stopping:** with proposed 10-row batches, two consecutive full
   batches containing 0 or 1 relevant role stop the query before another request;
   a batch with 2 resets the streak. Unknown relevance prevents confidently
   asserting the low-relevance threshold. Another relevant query on that platform
   remains active. No fixture uses a fixed position such as 50 as its cutoff.
6. **Reuse:** on the saved Apify rows, within-source unique processing admits at
   most 228 LinkedIn and 186 Seek identities before additional filters/merges.
   Restart and alternate output directory produce zero repeat paid submissions
   for compatible saved acquisitions and zero repeat successful assessments.
   Cross-source identity tests preserve distinct real jobs and source provenance.
   New fresh sessions exclude stale caches; changed evidence/JD/resume/policy
   invalidates only affected assessment reuse.
7. **Cost controls:** mocked event-cost reservations never exceed USD 0.50,
   including at restart or unknown submission. No speculative prefetch or optional
   salary events. Dataset paging cannot be counted as monetary savings. Missing
   enforceable cap/continuation marks limitation; never prefix-rerun to grow a batch.
   Report projected, reserved and actual costs separately, with actual unknown
   when billing telemetry is unavailable.
8. **Boundaries:** no new skill, automatic application record, suggestions before
   human selection, source-resume edits, employer contact or paid acceptance crawl.
   Updated docs no longer direct new runs to expand 24 hours to cover run delays.
9. **Reporting:** every configured query is accounted for as searched, cached,
   stopped, capped, failed, unavailable or unvisited at session stop. The report
   distinguishes confirmed/uncertain freshness and first qualifiers from exhaustive
   best matches. It returns useful partial results without asserting no other
   suitable jobs exist.

## Proposed defaults awaiting optional feedback

Batch size 10; relevance threshold below 20% for two consecutive full batches;
query-local stopping, platform stop once all queries stop/exhaust. These are
proposed tuning values, not validated provider capabilities or optimal thresholds.

## Implementation replay artifacts

The read-only `verify_saved_run.py` CLI in the retrieval skill reproduces source
raw/unique/duplicate/date counts and validates private adjudication fingerprints.
A private 35-job benchmark was saved beside the original checkpoint, with six
relevant, 18 irrelevant and 11 uncertain adjacent roles, based on title and duties
independently of candidate fit. It contains IDs, labels, reasons and description
hashes; it is excluded from Git. This is a deliberately mixed diagnostic set,
not a statistically representative estimate of search quality.

Invocation from the workspace:

```sh
./.venv/bin/python .agents/skills/job-retrieval/scripts/verify_saved_run.py \
  --checkpoint .state/stage1/20261008-fresh-24h/checkpoint.json \
  --benchmark .state/stage1/20261008-fresh-24h/relevance-benchmark.json
```

Observed: Seek 282/186/96; LinkedIn 410/228/182; all 410 LinkedIn entries calendar
only; all saved Seek task filters two days. The utility checks provenance and
label fingerprints, not whether the model would independently agree with labels.

## Integration verification

Before final review repairs, the integration branch passed 139 Python tests,
the JavaScript discovery bridge fixture checks, shell syntax validation, all four
job-skill validators and strict validation of all six OpenSpec changes. Tests
used local fixtures and mocked connectors; no paid provider searches were run.

Parallel standards and spec reviews used the user-approved baseline a79c094.
They identified three repair requirements: reconcile configured batch caps,
require an inspected enforceable paid-charge contract, and check shared caches
before rejecting acquisition for exhausted budget. Fixes were merged in 613ad6c;
the targeted spec recheck confirmed resolution without concrete regressions.
Final validation passed 144 Python tests (77 seconds), bridge fixtures, shell
syntax, skill validators and strict OpenSpec validation. The configured-coverage
test now follows the configured searches instead of assuming 108 combinations.

Five added public-interface repair cases verify default blocking without a charge
contract, configured cap/connector ceiling forwarding, later-query cache reuse
with exhausted allowance, unknown-submission reconciliation, and 35 adjudicated
relevance labels. The latter admits six relevant and 11 uncertain jobs while
excluding 18 irrelevant jobs; synthetic fixtures expose policy behavior without
committing private descriptions. Original private benchmark fingerprints also
passed read-only validation.

Limitations remain explicit: current actors have no verified nonrepeat cursor;
non-24-hour LinkedIn filter support remains unverified; calendar dates are not
exact timestamps; recorded reservations are not actual billing telemetry.
The USD 0.50 allowance covers Apify retrieval, excluding evidence embeddings and
Codex usage. Relevance replay checks policy enforcement of adjudicated labels,
not the accuracy of future model judgments or guaranteed monetary savings.
No verified charge-cap contract is shipped for the installed paid connectors:
new paid Seek/LinkedIn acquisitions are blocked until their enforcement support
and applicable pricing are inspected. Compatible cache reuse and free Indeed
acquisitions do not require that paid contract. Unsupported controls are reported,
never replaced by invented provider inputs.
