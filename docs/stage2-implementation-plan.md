> Historical API implementation plan. Superseded by
> `openspec/changes/codex-led-job-search`; current runs use Codex judgments.

# Stage 2 implementation plan

Status: implemented and verified with 76 passing local tests, a passing live quality
fixture, and three successful fresh 45-job benchmarks. See
[implementation and acceptance](../reports/2026-10-06-stage2-implementation.md).

## Acceptance contract

The benchmark workload is 45 retained jobs, approximately 1,100 original JD units classified as scoring requirements, and at least two text-extractable resumes. Known eligibility failures are excluded before evidence retrieval. Zero eligible jobs is a valid successful result.

| Criterion | Required evidence |
| --- | --- |
| Correct scoring | Complete frozen requirements; verified source-linked support for positive fit judgments; resume excerpts for positive coverage judgments; reproducible calculator totals and strict >75 qualification |
| Reliable results | Malformed or incomplete outputs cannot become scores or successful reports; bounded recovery handles transient faults; unrecoverable faults produce explicit failed/incomplete status |
| Runtime | Three comparable fresh benchmark runs complete every eligible job within 600 seconds; target approximately 300 seconds; faster results are acceptable |
| Total time | Stage 2 monotonic wall-clock duration, including initialization, eligibility, extraction, retrieval, judgments, repairs, and log commit |
| Total cost | Numeric Stage 2 cost estimate reconciled to metered request usage, including extraction, scoring, embedding calls, and accounted paid retries |
| Telemetry completeness | No accepted final scored-job record or Stage 2 summary has null elapsed or cost; unknown billable usage prevents success |

A deadline alone does not satisfy the runtime criterion: all eligible jobs must finish. No implementation can guarantee that providers never fail or that usage from every interrupted request is immediately recoverable. The enforceable requirement is that such failures never silently produce accepted results, omitted jobs, or fabricated cost.

## Architecture and boundaries

Add `scripts/stage2_runner.py` as the supervisor and `scripts/metered_api.py` as the shared API wrapper. Reuse `stage2_prepare.py`, `vault_evidence.py`, `score_job.py`, and `pipeline_log.py`. Use the existing OpenAI SDK and standard-library concurrency; do not introduce an agent framework.

The supervisor owns scheduling, deadlines, private checkpoints, validation, calculations, and log writes. Model calls perform requirement extraction and semantic judgments; each scoring call receives one job packet and returns structured judgments only. Initial concurrency is four, configurable and tuned by benchmark. These are concurrent API workers, independent of native desktop sub-agents.

Preserve 35/35/30 category budgets, documented absent-category redistribution, priority weights, strengths, threshold, resume tie-break, verified-vault restrictions, and eligibility/manual-review behavior. Stage 3 and destination approval rules remain separate stages.

Direct scoring calls send JD text, relevant verified evidence/source excerpts, and resume excerpts to the model provider. Existing hybrid mode already sends vault text for embedding, but scoring is a distinct data flow. Document that flow, minimize packets, use supported retention settings, and keep private content out of public logs. Inspect linked local sources; fetch remote sources only when necessary to inspect support, within the same measured budget.

## Implementation order

### 1. Metering and completion contract

- Define one usage ledger per Stage 2 run, with stable attempt IDs, job hashes, response/request IDs, resolved model, processing tier, token breakdown, versioned rates, cost, timestamps, and status.
- Persist usage immediately after each response, including invalid responses that require a paid repair. Keep SDK retries explicitly controlled so automatic retries cannot hide attempts or charges.
- Validate the configured model and rate card before starting work. Respect the requested Luna 6/high configuration when supported by the selected API; never silently substitute another model.
- Count cached input, applicable cache writes, and output correctly. Reasoning already included in output is not charged twice.
- Extend embedding calls to report usage through the same wrapper/accounting interface, including Stage 2 preflight if needed. Account for discovery/index initialization in separately scoped pipeline totals when performed before Stage 2.
- Record transport ambiguity explicitly. Recover usage using retained provider identifiers where supported; otherwise mark telemetry incomplete and fail acceptance.
- Record `elapsed_seconds`, `cost_estimate_usd`, `usage_scope`, `cost_complete`, `model`, and rate-card identity in the final Stage 2 summary. Token-based cost is an estimate, not an invoice.

### 2. Preparation and requirement integrity

- Read refreshed verified condition profile and resume text once. Strengthen clear work-rights alternatives and enrollment conditions without treating ambiguity as failure.
- Reuse grouping for identical company, position, and JD text. Retain separate original job IDs and condition records.
- Extract exact original JD spans with stable requirement IDs, Skills/Experience/Domain categories, and priorities. Assign IDs in Python after validating spans.
- Include responsibilities, seniority, scope, and domain; classify non-scoring education and boilerplate explicitly rather than silently dropping them.
- Freeze the manifest before retrieval. Reject missing, invented, changed, or duplicate requirements in downstream judgments.
- Automated span checks establish wording integrity, not semantic extraction completeness; verify coverage with reviewed JD fixtures and benchmark audits.

### 3. Evidence packets and retrieval

- Own one retrieval client/service lifetime with explicit configuration; remove dependence on inherited agent environment variables.
- Retrieve every frozen requirement with its full original wording and literal JD terms. Preserve hybrid/keyword mode selection; no silent fallback from hybrid.
- Bound OpenAI embedding and Chroma query batches separately; add clear timeouts and privacy-safe error codes. Determine reliable chunk sizes from measured results rather than assuming a provider limit.
- Reuse warm clients and in-memory query deduplication. A live health check must replace trust in a static READY marker when filesystem transport remains necessary.
- Build a private job packet with requirement IDs, verified claims, source excerpts, and both resumes. Retrieval similarity is never a scoring judgment.

### 4. Bounded parallel judgment

- Four workers initially; one job per scoring call. Supply the frozen manifest, evidence packet, rubric, and resume excerpts.
- Require structured strengths, supporting citation IDs, reasons, and resume excerpt references. Python controls categories/priorities from the manifest and calculates totals.
- Validate response completeness, citation eligibility, quoted source/resume spans, condition consistency, and arithmetic. Semantic support remains a model judgment assessed against reviewed examples.
- Retry only the invalid job, at most once, within the remaining global budget. Bounded repair may correct structure; it must not invent evidence to satisfy validation.
- Use a shared 600-second deadline; constrain queue waits, request timeouts, and output sizes. Cancel pending work and mark incompleteness on overrun.
- Persist validated checkpoints atomically under private run state. Fingerprint JD, vault/source inputs, resumes, rubric, and model configuration. Do not persist embedding vectors or query caches contrary to current retrieval rules.

### 5. Logging and runner integration

- Extend `pipeline_log.py` with a Stage 2 terminal summary and complete scored-job telemetry using consistent names. The supervisor is the single writer.
- Maintain one final condition result per original job. Failed gates receive no fit or resume score. Every eligible original job receives one final score record.
- Per-job elapsed is measured duration including its queue/work/retries; Stage 2 elapsed is wall time, not the sum of concurrent durations. Shared extraction/retrieval cost allocation is labeled explicitly and reconciles without double counting duplicated JDs.
- Store pending records privately until complete. If public logs record failures, use explicit failed status and incomplete accounting; they must not look like successful numeric measurements.
- Route `run.sh` and `docs/02-categorize-score.md` through the runner after discovery. Remove duplicate manual timing/log writes and reliance on the parent CLI finalizer for Stage 2 costs.
- Preserve the existing legacy scoring ledger schema. Identify any remaining full-turn CLI estimate as a separate scope, never add it to API totals as though it were the same measurement.
- Update AGENTS.md, README, scoring documentation, and privacy/data-flow descriptions together so agents follow the implemented contract.

## Verification and benchmark

Use local deterministic fixtures first, then metered live scoring of retained private JDs. No new source crawl is needed to establish Stage 2 runtime.

1. Extend unit coverage for arithmetic, gates, exact requirement identities, positive citations, resume spans, usage pricing, cached tokens, applicable cache writes, missing usage, and summary reconciliation.
2. Exercise integration faults: invalid JSON, omitted requirements, wrong job IDs, forged citations, rate limits, timeouts, service death, interrupted responses, duplicate callbacks, and restart/resume. Recoverable faults must remain within budget; unrecoverable faults must not publish accepted results.
3. Create reviewed representative fixtures, including seniority/scope gaps and previously problematic requirements. The prior generated audit outputs require review before being treated as ground truth.
4. Run three fresh representative benchmarks without reusing completed scoring checkpoints. Include initialization, all retrieval and repairs, and log finalization. Record phase times, request counts, peak concurrency, token usage, cost, and outcome for each run.
5. Tune concurrency, packet size, and output length using measured bottlenecks. Never omit requirements or skip evidence checks to hit the deadline.
6. Declare completion only when correctness fixtures, failure behavior, cost reconciliation, and all three runtime benchmarks pass. Otherwise report the failed criterion and measured bottleneck.

Provisional time budget: preparation 30s, extraction/coverage validation 90s, retrieval 60s, parallel judgments 300s, final validation/repair/logging 60s: 540s. These are engineering targets, not measured results.

Stage 2 API cost includes extraction, scoring, and embeddings. Full-workflow cost additionally requires source/preflight charges and any attributable Chroma fees or an explicit shared-service allocation policy. An API subtotal must never be labeled total workflow cost.
