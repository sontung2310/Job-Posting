# Simplified workflow verification

Implemented for GitHub issue #1 on `codex/simplify-job-search`, from baseline
`e2addcc`. The active procedures are job-retrieval and job-scoring; the router and
three competing procedural documents were removed. Global agent rules contain
only orientation and shared protections. References define connector and score
facts without another workflow.

## Behavioral checks

All 91 Python tests passed, along with Node bridge fixtures, shell syntax and
whitespace checks. Coverage includes default/override/longer discovery windows,
fixed endpoints across resume, provider filter coverage, unsupported source
periods, unreliable dates, Actor reconciliation, frozen requirements, source and
resume support, score arithmetic, immutable results, malformed-job isolation,
partial/empty handoffs, fixture isolation, source-free saved scoring, readiness
reuse and explicit CLI score-ledger idempotence.

The three public assessment interactions are prepare, requirements and judgments.
Returned templates hide copied fingerprints and internal artifact names. Helpers
save validated outcomes and condition/scoring/suggestion records automatically;
explicit CLI runs also record score drafts for real completed-turn finalization.

## Saved-workload comparison

One previously inspected saved JD, the same verified career facts, the same two
resume PDFs and the same reviewed judgments were used in keyword-only mode.
Eight original units and six scored requirements remained accounted for. The
compatibility match and every Resume Coverage score were identical, with no
assessment failures. Unknown saved discovery coverage remained explicitly partial.

| Measurement | Before | After |
| --- | ---: | ---: |
| Normal assessment helper interactions | 5 | 3 |
| Procedure/reference files considered | 7 | 5 |
| Words in those instruction files | 3,300 | 1,846 |
| Cold mechanical preparation/retrieval/validation | 0.897 s | 0.941 s |
| PDF extractions during cold assessment | 6 | 6 |

The three always-loaded active procedure files contain 1,231 words after cleanup;
the after column above conservatively includes both optional reference documents.
The word comparison excludes unchanged vault rules, configuration and job/evidence
packets. It is not a measurement of full-turn tokens or total model context.

Warm preparation took 0.016 seconds and made no additional PDF extractions.
The cold timings are single observations of mechanical work, excluding fresh
semantic reasoning and job-source calls. They demonstrate no cold-run speedup.
The measured improvements are fewer interactions and approximately 44% less
procedure/reference text, not a guaranteed faster full production run.

Detailed benchmark inputs/results remain private under
`.state/simplify-benchmark/`. Native tokens/cost remain unavailable; no fabricated
CLI event or ledger was created for this native benchmark.

## Standards review

One finding was fixed and independently rechecked: external fixture sessions now
keep readiness, condition profiles and implicit logs in their own workspace.
Tests confirm the main state and logs remain unchanged. One provably synthetic
fixture condition record was removed from the main daily log with a private
backup; non-fixture records were preserved. The final saved-data check restored
readiness from the real verified profile and resumes.

## Spec review

Both findings were fixed and independently rechecked: malformed submission rows
cannot discard valid later jobs, and requirement responses include discovery
coverage, every original job's outcome and unresolved progress, including gates.
No remaining blockers were reported by either review axis.

## Scope limits

No paid discovery submission, embedding request, application write, cover letter
or source-resume modification occurred. Actor input schemas were checked through
non-submitting reads. Provider account access and full live performance remain
unverified. No live acceptance search was necessary for the local checks; observe
full timing during an authorized normal production run rather than extra paid
benchmarks. Approved preparation and separate cover-letter approval are preserved.
