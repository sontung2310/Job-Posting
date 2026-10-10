# Implementation checklist

Implemented on `codex/simplify-job-search` for GitHub issue #1.
[Verification and measured scope](../../../docs/simplify-workflow-verification.md)
record local acceptance; live provider access and full production timing remain
unverified. This checklist is the implementation worklist, not separate tickets.

## 1. Establish instruction ownership

- [x] Inventory active skill/document/launcher instructions; assign a single owner to each rule and procedure.
- [x] Make retrieval and scoring self-contained procedures; move reference-only facts/contracts to necessary references and retire duplicated procedures.
- [x] Reduce global agent instructions to orientation and shared guardrails; preserve evidence, privacy, approval, immutable-resume and paid-retry protections.

## 2. Consolidate readiness and configurable discovery

- [x] Reuse one readiness implementation in native skills and launcher modes, with relevant fingerprint reuse and path-specific credentials/cloud checks.
- [x] Resolve lookback override/configuration/default 24; persist duration and exact fixed run-start endpoints and reject conflicting resume options.
- [x] Update provider filters, local freshness validation, coverage, error messages and legacy recovery for arbitrary positive integer lookbacks; report unsupported source periods honestly.

## 3. Consolidate assessment interactions

- [x] Replace the exposed condition/freeze/packet/calculate/finalize coordination with prepare, requirement submission and judgment submission interactions on existing helpers.
- [x] Hide internal artifact names and fingerprints behind returned run/job handles and generated templates; preserve independent frozen/retrieval provenance validation.
- [x] Keep failed gates before retrieval, manual-review semantics, all-resume support, score rules, every-original-job outcomes, qualifying suggestions and privacy-safe idempotent logs.
- [x] Preserve repairable incomplete work, immutable finalized results, changed-input invalidation and legacy saved-job handoffs without hidden source searches.

## 4. Cut over and remove obsolete surfaces

Depends on sections 1–3 being ready; migrate active callers together.

- [x] Update full-run launcher to retrieval then scoring, and saved-job mode to scoring only; remove the job-search router and all active references.
- [x] Retire redundant agent-facing commands, wrapper modules and obsolete tests after preserving their useful behavior; preserve private data and historical records.
- [x] Update user-facing usage and references so there is one usable procedure per skill and no competing numbered workflow.

## 5. Verify behavior and efficiency

- [x] Protect the previously approved public test areas through launcher and existing discovery/assessment helper seams; use saved external responses and actual local validators.
- [x] Cover default/override/48-hour/longer windows, invalid values, provider filters, unreliable timestamps and resumed fixed endpoints.
- [x] Retain frozen-ID/citation/resume-line/gate/arithmetic/immutable-result/Actor-recovery/all-job/empty/partial-coverage regression behavior.
- [x] Verify two independent skills, correct full-run handoff, source-free scoring-only execution, keyword-only cloud independence and unchanged approval/telemetry behavior.
- [x] Measure equivalent saved-data instruction loading, mechanical interactions, readiness/embedding reuse and scoped elapsed time; inspect semantic quality without dropping jobs.
- [x] Evaluate live acceptance necessity and record scope: no live submission was needed for local verification. Full runtime measurement remains for an authorized production run, without extra paid benchmarks.
