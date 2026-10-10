# Scoring reference

Candidate Evidence Fit measures demonstrated verified career evidence; Resume
Coverage measures what each current resume shows. The two scores are independent.
The calculator owns arithmetic; configuration owns the exclusive qualification
threshold, currently 75. Exactly the threshold remains below threshold.

| Category | Budget | Meaning |
| --- | --- | --- |
| Skills | 45 | Technical capabilities and relevant certifications. |
| Experience | 35 | Delivery, seniority, leadership and requested scope. |
| Domain | 20 | Operating/industry knowledge required to perform the work. |

Requirements have priority 3 (essential/high importance), 2 (standard) or 1
(preferred). Use these candidate judgments:

| Judgment | Credit | Evidence standard |
| --- | --- | --- |
| `direct` | 100% | Demonstrates the requested capability and material scope. |
| `strong_transfer` | 85% | Demonstrates comparable complexity, ownership and delivery; the remaining change is a tool, platform or context with a small learning gap. |
| `partial_transfer` | 50% | Demonstrates related capability with a material gap in scope, depth, ownership or seniority. |
| `missing` | 0% | A confirmed capability gap, supported by an explicit user statement or verified limitation. |
| `unknown` | 0–100% range | Available evidence cannot establish the capability or a confirmed gap. Explain the specific evidence or clarification needed. |

Legacy `transferable` inputs retain 50% credit; new judgments use the explicit
transfer levels. These credits are screening policy, not probabilities of job success.

Absent category budgets redistribute proportionally; existing half-up rounding
and resume tie-breaks are preserved. Education is a condition where explicitly
required, not a points category. Benefits and standalone keywords earn no points.

For transfer, explain the demonstrated capability, how it carries into the job,
and the remaining gap. Strong transfer requires comparable delivery evidence;
learning potential alone is insufficient. Preserve compound wording and judge
its material scope: a change of cloud or industry does not automatically halve
credit, while an unmet core expert skill or leadership scope remains a material gap.
Score Domain on knowledge the work demands; employer size, startup funding and
marketing descriptions alone do not establish an industry requirement.

An empty Obsidian search is an evidence limitation. Inspect retrieved sources
and current resume lines before choosing `unknown` or confirming a gap.
Positive candidate credit
needs inspected verified claims and sources; positive resume credit needs exact
supporting lines. Resume coverage uses direct/strong/partial/missing, with missing
meaning the inspected resume omits support; it does not prove a candidate gap.

Unknown candidate requirements retain their full allocated weight. The lower
bound uses verified earned points; the upper bound adds unknown allocated points.
Evidence coverage is the percentage of allocated weight with a known judgment,
including confirmed gaps. Qualify only when the rounded lower bound exceeds the
threshold; reject when the rounded upper bound cannot exceed it. Otherwise return
`evidence_review`, publish the range and questions, and keep the report
NONSELECTABLE. Clarify only the unknowns that could affect the decision.
Provisional evidence-review judgments can be resubmitted against the same unchanged
packet. Changed career evidence requires preparation of a new scoring run.

Compatibility match output contains exactly category (AI Agent, Computer Vision
or Hybrid), recommended_resume and ATS_score. ATS_score means Candidate Evidence
Fit's conservative lower bound, not an employer ATS prediction. Outputs retain the
score range, evidence coverage, unknown requirement IDs, all resume coverage scores,
condition/manual-review status and private requirement evidence tables.

Detailed suggestions are generated only for human-selected candidates by job-suggestions.

The helper emits the current decision templates and run/job handles. Its three
public interactions own private intermediate artifacts and idempotent records.
Completed successful assessments are immutable; failed or missing work remains
repairable. Changed inputs require revalidation and a new scoring run when an
existing result is finalized.
Prepared runs snapshot the scoring policy. Changed weights or credit rules require
a new scoring run; saved outcomes retain their original scores.

Native unavailable token/cost telemetry remains null. Explicit CLI ledger runs
use real completed-turn usage for a separate full-turn allocation; missing usage
fails CLI finalization. Concurrent durations are not summed as wall time.
