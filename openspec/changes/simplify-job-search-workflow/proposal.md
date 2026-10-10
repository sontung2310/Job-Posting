## Problem Statement

The personal job-search workflow is difficult to understand and operate. A third
router skill coordinates two substantive skills, while procedural instructions
are distributed across skills, numbered workflow documents and global agent
rules. The user cannot easily tell which instruction owns a step or which source
wins when they conflict.

Assessment exposes its implementation to Codex: several ordered commands,
intermediate filenames, copied fingerprints and repeated readiness checks. That
coordination consumes attention and tool calls without improving the semantic
judgments. Discovery also hard-codes 24 hours even though the user wants a
configurable lookback, including 48 hours or longer.

The existing evidence validation, score arithmetic, private recovery records and
safe paid-submission recovery are useful. The cleanup must simplify how they are
used while preserving their guarantees.

## Solution

Provide exactly two substantive workflow skills: job-retrieval and job-scoring.
The full-run launcher asks Codex to execute retrieval and pass its saved output
to scoring. Retrieval-only and scoring-only invocation remain available without
a third router skill.

Each skill contains its complete procedural sequence and completion criteria.
Global agent instructions contain a brief orientation and only shared privacy,
evidence, approval and paid-retry guardrails. Reference documents contain facts
and contracts, not a competing workflow. Obsolete and duplicate active material
is removed or consolidated during implementation.

Discovery resolves its lookback from the user override, then configuration, then
a 24-hour default. That duration defines a fixed run-start window which is saved
and preserved across retries and resume.

Scoring uses three interactions with the existing mechanical helpers: prepare
the saved jobs; submit conditions and classifications to obtain evidence; submit
judgments and concise suggestions to obtain validated results. Helpers manage
intermediate files, fingerprints, arithmetic, recovery and logs. Codex continues
to inspect the original JDs and sources and make all semantic judgments. It
presents the final report and waits for approval.

## User Stories

1. As the personal user, I want only two workflow skills, so that their responsibilities are easy to remember.
2. As the personal user, I want a full run to execute retrieval followed by scoring, so that I do not coordinate the handoff manually.
3. As the personal user, I want retrieval alone, so that I can collect jobs without starting assessment.
4. As the personal user, I want scoring alone on saved jobs, so that I can assess them without another paid search.
5. As the personal user, I want a short global instruction document, so that the essential shared rules are easy to read.
6. As Codex, I want one owner for each procedural instruction, so that skills and documents cannot give conflicting steps.
7. As Codex, I want each skill to contain its complete phase procedure, so that I can execute it without following a chain of workflow documents.
8. As Codex, I want references loaded only for relevant facts or contracts, so that routine runs do not load unrelated preparation instructions.
9. As the personal user, I want a 24-hour default lookback, so that ordinary runs preserve the current search preference.
10. As the personal user, I want to request 48 hours or a longer lookback, so that I can cover periods when I did not search.
11. As the personal user, I want an explicit run override to take precedence over configuration, so that a one-off search does not require editing persistent settings.
12. As the personal user, I want the effective lookback and cutoff shown in coverage, so that I know what period was searched.
13. As the personal user, I want resumed discovery to keep its original window, so that jobs are filtered consistently even when collection is delayed.
14. As the personal user, I want source filter limitations reported, so that a narrow provider filter cannot masquerade as coverage of my requested period.
15. As Codex, I want one reusable readiness implementation, so that launcher and skill invocations check the same evidence and resumes.
16. As the personal user, I want unchanged readiness and vector inputs reused, so that unnecessary checks and embedding charges are avoided.
17. As the personal user, I want source credentials required only for discovery paths that need them, so that saved-job scoring remains independently usable.
18. As Codex, I want prepared jobs with complete JDs, a verified profile and numbered resume text, so that I can judge conditions and requirements accurately.
19. As Codex, I want to submit conditions and classifications together, so that I do not manage their ordering or intermediate filenames.
20. As the personal user, I want a known work-rights or required-degree failure to stop retrieval and scoring for that job, so that ineligible jobs do not receive misleading scores.
21. As the personal user, I want ambiguous conditions to proceed with a manual-review flag, so that uncertainty is visible rather than treated as a known failure.
22. As Codex, I want the helper to freeze requirements and retrieve evidence after accepting my classification, so that evidence requests preserve the complete original wording.
23. As Codex, I want exact citation and resume-line identifiers in the evidence packet, so that I can explain support without copying provenance metadata between files.
24. As the personal user, I want every positive judgment grounded in inspected verified sources and exact resume lines, so that similarity alone cannot earn points.
25. As Codex, I want one judgment submission to validate and save scores and suggestions, so that I do not call separate calculators and loggers.
26. As the personal user, I want every retained job accounted for, so that partial failures cannot be reported as successful empty runs.
27. As the personal user, I want completed work reused and invalid work repairable, so that interruption does not force a whole-run restart.
28. As the personal user, I want finalized assessment revisions to use a new scoring run, so that saved results and logs cannot silently disagree.
29. As the personal user, I want every qualifying job presented with concise sourced advice, so that I can decide which candidates to approve.
30. As the personal user, I want private evidence, resumes, application records and historical reports preserved, so that code cleanup does not remove my data.
31. As the personal user, I want approval required before application-record writes, so that discovery and scoring do not create preparation records automatically.
32. As the personal user, I want native unavailable telemetry kept unavailable and CLI usage finalized honestly, so that workflow simplification does not invent cost or timing.
33. As the personal user, I want local saved-data checks before any necessary live test, so that cleanup does not spend money on repeated implementation crawls.
34. As the personal user, I want measured comparisons of instruction loading and mechanical interactions, so that efficiency improvements are demonstrated rather than assumed.

## Implementation Decisions

- Retain job-retrieval and job-scoring as the only job-search workflow skills. Remove the job-search router and update the launcher and all active callers at the same cutover.
- The launcher owns only invocation, run options and CLI finalization. It expresses the two-skill sequence without repeating their procedures. Scoring owns the assessment report; retrieval owns its jobs and coverage handoff.
- Global agent instructions retain only a brief skill orientation and shared verified-fact, privacy, approval, immutable-resume and unknown-paid-submission rules. Phase steps, arithmetic details, source configuration and reporting contracts move to their respective owners.
- Skills are the authoritative procedural instructions. Reference documents may define connector details, terminology and data contracts. Remove or consolidate procedural duplication rather than retaining conflicting copies with a precedence disclaimer.
- Keep approved destination preparation separate and load its schemas and instructions only after report-bound approval. The separate cover-letter approval process remains unchanged.
- Resolve positive integer lookback hours using explicit user override, configured value, then default 24. Reject invalid selected values instead of silently coercing them or applying a smaller duration.
- Persist effective duration, run-start time and exact window endpoints once. A resume uses that saved window and rejects an attempted conflicting override before source calls.
- Source filters must cover the requested window, using a supported broader filter when needed, followed by exact local timestamp filtering. Preserve existing caps and show limitations; never silently narrow the window or substitute job sources.
- Reuse one readiness implementation for the launcher and independently invoked skills. Cache validity depends on the relevant current evidence, profile, resume, configuration and validator inputs. Credentials and cloud prerequisites are checked only for enabled paths.
- Consolidate the assessment interface into prepare, requirement submission and judgment submission. Each accepts a run reference and jobs or job groups. Successful submissions return next-needed information and current coverage, rather than requiring Codex to locate internal files.
- Requirement submission validates Codex conditions and complete JD classifications, saves accepted conditions, freezes eligible requirements and invokes existing batch retrieval. Known condition failures skip all requirement retrieval and scores. Helpers validate conditions; they do not interpret their meaning.
- Judgment submission binds to independently persisted original jobs, accepted conditions, frozen requirements and retrieval provenance. It validates cited current claims, supporting sources, resume lines and qualifying suggestions, then calculates and saves outcomes and privacy-safe logs once.
- Helpers calculate necessary provenance values and manage private internal artifacts. Codex supplies decisions and support identifiers, not copied fingerprints, internal filenames or assembled calculator inputs. Existing stable IDs, snapshots and atomic-write utilities are reused.
- Failed or missing reviews remain repairable and visible. Preserve finalized-result immutability, changed-input invalidation and safe discovery reconciliation. Support saved legacy handoffs without paid resubmission; require a new scoring run when an old result cannot be safely revalidated.
- Preserve Candidate Evidence Fit and Resume Coverage definitions: Skills 35, Experience 35, Domain 30; priority 3/2/1; direct/transferable/missing credit 100%/50%/0%; existing redistribution, half-up rounding, resume tie-break and configured exclusive threshold. Preserve the three-key compatibility match output.
- Reuse the existing keyword/hybrid retriever. Keyword-only operation remains local; hybrid permits the existing embedding model and Chroma operations only. No generation API fallback or new retrieval service is introduced.
- Delete redundant active commands, wrapper modules, tests and document procedures after migrating their useful behavior. Keep a calculator module when its arithmetic and validation earn their place; it need not remain a separate agent-facing command.
- Preserve full configured search and assessment coverage over the runtime target. Keep real scope-specific timing, unavailable native usage and separate CLI completed-turn finalization.

## Testing Decisions

- Reuse the five public behavior areas previously confirmed by the user: scoring/evidence validation, discovery recovery/filtering, saved-job handoff, keyword-only operation and launcher behavior. No additional user interview is required for those unchanged expectations.
- Prefer the launcher as the highest existing seam for full-run, retrieval-only and scoring-only scenarios. Use the existing discovery and assessment public helper seams for targeted failure and support-validation cases that cannot be observed through the launcher economically. Avoid new test-only seams.
- Good tests observe returned progress, saved public-contract results and external effects. They do not assert internal filenames, private method calls, module count or a particular implementation decomposition.
- Reuse prior saved connector-response, bridge, calculator, assessment-handoff, readiness and embedding-boundary tests. Replace obsolete command-protocol tests after equivalent behavior is protected through the consolidated interface.
- Use temporary private fixture directories, saved JDs and real text-extractable synthetic resumes. Substitute only external connector/cloud boundaries; run actual local validation and arithmetic. Source resume files and existing personal records must remain unchanged.
- Cover default 24 hours, override precedence, 48 hours, a longer period, invalid values, exact window endpoints, post-run-start dates, unreliable dates and resumed-window conflicts. Test provider filter translation against confirmed schemas without paid submissions.
- Cover every JD unit, omitted frozen requirements, forged citations, missing or forged resume lines, gate failures, manual review, exact-threshold nonqualification, all current resumes, complete empty jobs and partial source coverage.
- Cover repaired failures, immutable finalized revisions, changed evidence/profile/resumes, idempotent logs, unknown Actor submissions and confirmed Actor reconciliation. No source calls are allowed during scoring-only checks.
- Verify active skill/document ownership and removal of the router references. Every documented skill invocation and public helper interaction must be usable without consulting a competing procedure.
- Measure a saved-data before/after comparison with the same workload, evidence and retrieval mode: instruction material loaded, mechanical interactions, readiness/embedding requests and elapsed time. Report semantic inspection separately from mechanical validation and preserve unavailable telemetry. Efficiency must improve without dropping coverage or weakening validation; full-production runtime is not inferred from fixtures.
- A live acceptance search is conditional on necessity and follows the existing one-platform, one-pair, maximum-three-result allowance. Do not perform repeated paid benchmarks or a full production crawl merely to validate cleanup.

## Out of Scope

- Running discovery, implementing this specification, installing new services or performing paid acceptance as part of specification authoring.
- Automatic applications, employer contact, source-resume edits, initial Obsidian/Notion writes or cover-letter generation.
- Changing scoring budgets, thresholds, categories, evidence eligibility or approval semantics.
- New job sources, generic web/browser substitutes for configured sources, a custom worker scheduler, a workflow engine or a direct generation API.
- Removing private evidence, resumes, application history, saved source responses or historical reports/logs.
- A guaranteed full-production runtime or a fixed percentage speedup before measurement.

## Further Notes

This follows the implemented Codex-led change and supersedes its three-skill
layout and mandatory 24-hour duration at implementation cutover. It preserves
the run-start cutoff rule while making the duration configurable. Until cutover,
the current workflow remains active; the specification does not change behavior.

The project has no documented tracker/triage setup. The invoked skill recommends
running `/setup-matt-pocock-skills`. The repository's enabled GitHub Issues is
used for this specification, with the explicitly required ready-for-agent label.
No separate implementation tickets or issue dependency graph are created here.
