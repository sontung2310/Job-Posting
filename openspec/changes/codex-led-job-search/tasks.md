# Implementation checklist

Implementation completed on `codex/codex-led-job-search`. See
[verification scope](../../../docs/codex-led-implementation.md). Live-provider
acceptance and full production timing are deferred, not claimed as tested.

## 1. Simplify the runtime

- [x] Preserve useful extraction/citation/resume-line/source checks from Stage 2, then delete generation orchestration, client, rate card and obsolete tests.
- [x] Reuse local/hybrid retrieval, verified profile loading, grouping and score arithmetic; consolidate files where that reduces work.
- [x] Ensure Codex owns condition and evidence judgments and every calculator entry point validates their support.
- [x] Make OpenAI/Chroma dependencies and keys hybrid-only; reuse unchanged index inputs and minimal honest embedding usage checks.
- [x] Simplify the discovery bridge while preserving saved Actor IDs, safe retries, pagination, freshness and duplicates.
- [x] Add test selection for one platform and one title/location with at most three results; prohibit automatic multi-platform test expansion.

## 2. Add focused skills and a short entry point

- [x] Create job-retrieval for preflight/source calls/normalization/checkpoints and job-scoring for conditions/evidence/scores/suggestions/report, with independent invocation and explicit completion criteria.
- [x] Keep job-search as routing only: retrieval, saved JSON handoff, scoring, overall coverage/time and links to separately approved preparation. Do not duplicate phase instructions.
- [x] Reuse private jobs/coverage JSON for the handoff; ensure scoring-only runs validate evidence readiness without source credentials or new searches, and preserve partial/empty discovery outcomes.
- [x] Reuse existing private checkpoints/results/logs; ensure all searches and retained jobs are accounted for without a new workflow engine.
- [x] Keep concise sourced suggestions for every qualifier; move extensive tailoring to approved package preparation.
- [x] Use one agent first; add native assessment workers only if measurements justify them, with disjoint jobs and root-owned shared logging.
- [x] Update run.sh, AGENTS files, workflow docs and README together; remove conflicting mandates and duplicated instructions.
- [x] Preserve private evidence/resumes/history and destination approvals; delete or reorganize code files where useful.

## 3. Verify responsibly

- [x] Pass local saved-response/fixture checks for tool arguments, dates, duplicates, Actor recovery, all-job coverage, source/line validation and score rules.
- [x] Verify no generation API calls, keyword-only operation without cloud dependencies, hybrid-only embedding calls, honest usage and no initial destination/resume writes.
- [x] Measure assessment on saved JDs and inspect semantic quality; do not use paid discovery while fixing local code.
- [x] Verify each skill independently and the local handoff: retrieval-only output, scoring-only resume, empty jobs, partial coverage and no hidden source submissions during scoring.
- [ ] Optional live acceptance: perform at most one necessary search on one selected platform with at most three results. Deferred; local checks required no new paid submission.
- [ ] If live acceptance is performed, save its response and diagnose failures locally. Another search after failure needs explicit authorization; never resubmit an unknown outcome. Not applicable to this local verification.
- [x] Record the scope and limitations of local verification and saved-JD assessment.
- [ ] Observe full runtime during an authorized normal production run, without extra paid benchmark crawls. No production crawl was launched for implementation acceptance.
- [x] Confirm functional success against design.md; report real coverage and timing, with overruns continuing rather than skipping jobs.
