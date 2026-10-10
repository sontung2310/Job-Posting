# Design: simple Codex-led job search

## Main goal

Codex completes the configured job search, judges jobs using verified career
facts, and presents qualifying candidates for approval. Small helpers handle
reliable data access and calculations. No separate OpenAI generation API is used;
only embeddings are allowed when hybrid search is enabled.

Target 10–15 minutes from preflight through final report. Full search and scoring
coverage takes priority over time. Announce overruns and continue useful work;
never shorten the workload to claim success.

## Workflow

1. **Prepare once.** Validate the vault, refresh the verified condition profile,
   check all resume PDFs and connector availability. Check embedding/index
   readiness only in hybrid mode. At least two resumes must have extractable text.
2. **Discover.** Codex invokes the configured Indeed plugin and LinkedIn/Seek Apify
   tools through small supervised batches. Helpers save responses and Actor IDs,
   normalize full descriptions, enforce the run-start 24-hour window and remove
   duplicates, including existing active/archive application records.
3. **Assess.** Codex checks work-rights and explicitly required degrees, extracts
   original JD requirements, calls existing batch retrieval, inspects claims and
   sources, and judges fit and each resume. Helpers validate IDs/citations/resume
   lines and calculate scores. Every retained job is accounted for.
4. **Report.** Present every qualifier with fit, resume coverage, sourced strengths,
   gaps, concise proposed changes and ambiguous conditions. Keep full evidence
   tables privately. Stop for explicit approval before application-record writes.

## Skill responsibilities and handoff

Use two substantive skills and one short entry point under `.agents/skills/`:

| Skill | Owns | Done when |
| --- | --- | --- |
| `job-retrieval` | Preflight, configured source calls, normalization, freshness, deduplication and discovery recovery | Every configured search is accounted for; normalized retained jobs and an honest coverage summary are saved |
| `job-scoring` | Conditions, JD requirements, evidence retrieval/inspection, fit, resume coverage, concise suggestions and approval report | Every supplied job has a validated assessment or explicit failure; every qualifier is reported |
| `job-search` | Route retrieval to scoring, present overall coverage/time, and point approved preparation to existing instructions | The full run is reported with its approval boundary and any incomplete work |

Each has a `SKILL.md`; `job-search` contains routing only. Source/tool details
belong to retrieval; evidence/scoring/report details belong to scoring. Shared
rules stay in AGENTS and existing references. No separate skills are needed for
conditions, deduplication, arithmetic, logging or each platform. The launcher
explicitly invokes `job-search`; the two focused skills remain independently
invocable and discoverable by the entry point.

The handoff reuses saved private JSON: normalized full jobs, run ID/checkpoint
reference, original cutoff and discovery coverage summary. Scoring reads that
snapshot and does not start source searches. Partial source coverage stays visibly
partial in the final report. Re-running scoring uses saved jobs; it never silently
re-runs retrieval. Independent scoring checks current vault/profile/resume and
hybrid readiness, reusing a valid run preflight rather than repeating it, and
requires no job-source credentials. A retrieval-only invocation returns saved
jobs/coverage without scores or an approval-candidate report.

Approved package preparation loads destination schemas and relevant resume
skills through existing instructions, after report-bound approval. Keep approval
flags and the separate cover-letter approval process unchanged.

Use one Codex agent by default. If measured assessment time is the bottleneck,
use available native Codex workers on disjoint job groups; root alone writes
shared logs and reports. No custom worker scheduler, new sidebar chats, per-job
CLI processes or direct-generation API fallback is needed. Single-agent execution
must still cover every job. Helpers may perform several mechanical operations
per call; they return progress so Codex retains control without excessive calls.

## What to keep, remove or update

These decisions are based on the reviewed working code, not only filenames.
The user permits deleting and restructuring code. Preserve useful behavior and
private data; do not retain a file merely for compatibility with obsolete code.

| Current area | Decision |
| --- | --- |
| `stage1_runner.py`, `stage1_mcp.js` | Keep useful checkpoint, Actor ID, pagination, retry, freshness and normalization logic. Simplify the bridge into bounded batches returning progress; remove whole-crawl loops and hard-coded workspace paths. Add single-platform/single-search test selection. |
| `stage2_runner.py` | Remove direct extraction/judgment orchestration. First move JD numbering, completeness checks, resume-line checks, citation validation and source-reading logic into an existing helper or one small `assessment_support.py`. |
| `metered_api.py`, `config/stage2_rates.json` | Remove generation client, pricing and quota machinery. Reuse only the minimal embedding usage/error checks needed by the existing embedding client. |
| `stage2_prepare.py`, `condition_profile.py` | Keep verified profile loading and identical-JD grouping; Codex owns condition interpretation. Simplify or merge preparation code if its remaining role is small. Regex may surface clauses, not make final semantic decisions. |
| `score_job.py` | Keep 35/35/30 arithmetic and resume selection. Ensure all entry points require validated conditions, citations and positive resume-line evidence. |
| `vault_evidence.py`, `index_vault_chroma.py` | Keep existing local/hybrid batch retrieval. Reuse unchanged index inputs; avoid repeated probes and re-embedding. No second retriever or mandatory new service. |
| `pipeline_log.py`, `scoring_ledger.py`, existing state | Reuse run IDs, private files and privacy-safe logging. Keep available CLI usage estimates with honest scope; do not create a new state engine or telemetry subsystem. |
| `run.sh`, credential launchers | Thin launch/preflight/finalization only. Invoke job-search once; remove duplicated workflow prose and generation API prerequisites. Require credentials only for enabled paths. |
| `requirements*.txt` | Base local dependencies only; OpenAI/Chroma optional for hybrid; Playwright remains optional for the separate source verifier. |
| `job_sources.py`, source-board config/docs | Preserve useful existing utilities and separate ATS/government verification; do not silently add extra sources to the default run. |
| `AGENTS.md`, career-vault rules, workflow docs, README | Shorten and reconcile at cutover. Keep guardrails in AGENTS, routing in job-search, phase steps in their focused skills, definitions in reference docs and configuration in YAML. Mark the prior API implementation plan historical. |
| Destination schemas, resumes, vault evidence, application records, historical reports/logs | Preserve evidence/privacy/approval rules and private data. No resume mutation. |

File names and directory layout above are suggestions, not required architecture.
Reuse existing checkpoint/result JSON and atomic writes. Save a completed result
per job/group and a small run summary; resume missing work and avoid duplicate
records. Revalidate changed evidence/profile/resumes before trusting old results.
No new `workflow_state.py`, versioned workflow state machine, batch-commit service,
or fixed multi-agent configuration is required.

## Success criteria

- Every configured search is attempted; complete discovery requires all searches
  successful. Current configuration expands to 108 combinations. Existing result
  caps remain unchanged and visible; completion does not imply uncapped enumeration.
- Every retained job receives a condition result. Known work-rights/required-degree
  failures have no scores; all other jobs get validated fit and all resume scores.
- Fit and coverage retain Skills 35, Experience 35, Domain 30; priorities 3/2/1;
  direct/transferable/missing credit 100%/50%/0%; category redistribution and existing
  rounding/tie-break. Fit must exceed 75 with the current threshold to qualify.
- Every scored JD requirement is preserved, retrieved and judged from inspected
  verified sources. Similarity alone earns no points. Positive resume judgments
  have exact supporting lines; unsupported seniority/scope cannot become direct.
- No direct generation API call or key requirement remains. Keyword-only mode
  works without OpenAI/Chroma packages/keys; hybrid uses embeddings and Chroma only.
- Every qualifier appears with concise sourced advice and manual-review flags.
  Zero new/qualifying jobs is valid when coverage is complete.
- No initial Obsidian/Notion writes, application submission, contact, resume edit
  or cover-letter generation occurs. Approved preparation repeats duplicate and
  provenance checks and respects false-by-default destination flags.
- Real total/phase timing and coverage are reported. Partial source/assessment
  failures remain explicit. Unknown usage is not zero; native unavailable token
  telemetry is not fabricated. Concurrent times are not summed into wall time.

## Testing without expensive crawl loops

Do most development with saved connector responses, synthetic fixtures and the
existing saved JDs. Check source arguments, response shapes, date filtering,
pagination, duplicate handling, interrupted Actor recovery, scoring and report
behavior locally. Confirm current tool schemas and account access through
non-submitting checks where available; schema knowledge alone does not prove
provider access.

Only when those checks pass and the retrieval path is ready, perform one necessary
live acceptance search on one selected platform. Example: **AI Engineer in
Melbourne**, on LinkedIn OR Seek OR Indeed. Use a maximum of three results where
supported; for Apify submit at most one Actor run. The other platforms must not
start automatically. Polling and reading that saved run are allowed; they are
not new submissions. If the outcome is unknown, reconcile it rather than retry.

Save the response for all later parsing/scoring checks. If the live test fails,
inspect it and fix locally; do not automatically submit a second paid search.
Explain the result and obtain explicit authorization before another live test.
No routine three-platform smoke, repeated paid benchmarks, or full paid crawl
is required for implementation acceptance.

Test the skills independently: retrieval uses saved connector responses and the
single live acceptance search when ready; scoring uses saved jobs and verified
evidence without any Apify submission. Check the JSON handoff locally, including
empty jobs, partial source coverage and scoring-only resume.

Use saved jobs to measure Codex assessment and audit evidence quality. The old
44-eligible-job API benchmarks took 525–597 seconds, mainly in judgment; they are
comparison data, not proof of new end-to-end performance. A single search proves
only that source path. Measure full 10–15 minute performance from an authorized
normal production run, including all searches, preflight and report. Do not
launch extra full crawls solely to manufacture benchmark evidence.

## Implementation order

Preserve useful local checks, remove generation calls, simplify discovery helpers,
add the two focused skills and short entry point, then update launcher and
instructions together. Validate locally before the one optional live retrieval
test. Avoid activating the new skills while
old instructions still mandate the deleted API runner. This change remains a
specification until implementation is requested.
