# Design: two skills and a smaller assessment interface

## Ownership

| Owner | Owns | Excludes |
| --- | --- | --- |
| Global agent instructions | Brief orientation and shared evidence/privacy/approval/retry guardrails | Phase procedures, score formulas, hard-coded lookback, command recipes |
| job-retrieval | Complete discovery procedure, coverage, recovery and saved handoff | Evidence scoring and approval-candidate report |
| job-scoring | Complete assessment procedure, all outcomes, recommendations and final report | New source searches and pre-approval destination writes |
| Launcher | Run options, retrieval-to-scoring invocation, CLI finalization | Repeated skill procedures and semantic judgments |
| Existing mechanical helpers | Readiness, checkpoints, retrieval, validation, arithmetic, atomic private writes and logs | JD interpretation and evidence-strength decisions |
| Reference documents | Necessary connector facts, score definitions and data contracts | Another ordered discovery/scoring workflow |
| Approved-preparation instructions | Destination-specific procedures after approval | Initial-run execution |

Exactly two workflow skills remain. Remove the router rather than replace it with
another coordinating skill. The full launcher invokes retrieval followed by
scoring; saved-job mode invokes scoring only. Independent retrieval returns jobs
and coverage and ends without assessing candidates.

## Instruction cutover

Audit each active rule or procedure and assign one owner. Absorb discovery,
assessment and report steps from numbered documents into their corresponding
skills. Retain a reference only when its facts or contract earn a separate lookup.
Delete emptied or redundant active documents and update their callers together.
Keep historical specifications/reports clearly historical; they are not active
workflow instructions.

Use the configuration and helper-generated contracts as the authority for values
and operational schemas. Skills describe decisions and completion criteria,
without requiring copied large JSON recipes. Approved preparation remains on
demand; there is no reason to load its schemas during normal discovery.

## Discovery window

Resolve lookback hours once: explicit run override, configured value, default 24.
Use positive integers; reject zero, negative, nonnumeric and fractional selected
values. Save effective duration, original run-start time and UTC endpoints. The
local interval is inclusive from run start minus duration through run start.

Resume never moves either endpoint. A new override that conflicts with the saved
window is an error before any source submission; a new window needs a new run.
Legacy checkpoints with trustworthy endpoints retain those endpoints. Infer a
legacy duration only when its saved window or documented format proves it;
ambiguous old state requires explicit recovery or a new run, never a paid retry.

Update all local checks, provider filters, coverage fields, diagnostics and test
selectors to use the selected duration. Provider filters may be coarser than the
user request: select a supported superset and filter exact reliable timestamps
locally. If no supported query can cover the period, expose a source limitation
and partial/failed coverage rather than silently searching only 24 hours. Result
caps remain visible and unchanged. Missing, calendar-only and relative labels
cannot establish freshness unless saved precision/observation metadata can prove
the entire posting interval belongs to the selected window; otherwise reject.

## Three assessment interactions

Names below describe responsibilities; implementation may choose concise command
names while preserving these interactions.

1. **Prepare saved jobs.** Resolve or reuse shared readiness and return a run
   reference, full original JDs, numbered units, verified condition profile,
   resume line IDs and saved discovery coverage. No source credentials/searches
   are required. Python manages fingerprints and private artifact locations.
2. **Submit conditions and classifications.** Accept Codex's condition decisions
   and unit classifications for jobs or groups. Validate original clauses and
   completeness. Failed conditions need no classifications and produce no
   evidence requests or scores. For other jobs, preserve accepted conditions,
   freeze requirements, use existing batch retrieval and return claims, source
   references, citation IDs and resume lines. External source inspection remains
   Codex-owned; source availability and support must be explicit.
3. **Submit judgments and suggestions.** Accept Codex's strengths, reasons,
   citations, resume-line support and concise suggestions. Bind them to the
   independent accepted inputs and retrieval record. Validate, calculate, save
   successful outcomes and write privacy-safe logs once. Return results,
   per-job failures, unresolved work and actual coverage/timing. Completion is
   inferred from all original jobs being accounted for, not a separate manual
   finalize command.

Codex reads and judges; Python handles ordering, bookkeeping and arithmetic.
Submissions may batch disjoint jobs to reduce calls, but never impose top-N or
time-based omissions. Helpers return progress to Codex rather than introduce a
new autonomous model runner or custom scheduling layer. If an explicit retry is
needed for an unavailable evidence operation, reuse the accepted requirements
and existing retrieval cache; do not require copying internal state files.

Existing private artifacts can stay as implementation details. Use returned
handles and generated input templates to avoid copied hashes and filenames.
Persist before billable operations and keep known Actor IDs/retrieval responses.
Incomplete or invalid jobs remain repairable; finalized successful assessments
remain immutable and revisions require a new scoring run. Every original job
still gets its own condition/outcome even when identical JDs share calculations.

## Consolidation rather than wrappers

Modify the existing helper interface and move its callers onto it. Remove old
agent-facing commands after equivalent behavior is covered; do not add three new
commands on top of six old commands and leave both workflows active. Preserve
deep mechanical modules such as validated arithmetic and retrieval, but retire
standalone entry points that the new skills no longer need.

Readiness has one implementation with discovery and saved-scoring contexts.
Relevant fingerprints determine reuse; source authentication is separate from
local scoring readiness. Keyword-only mode never initializes cloud clients.
Hybrid reuses current vectors and avoids repeated billable probes.

## Acceptance and limits

The two skills must each run through a complete documented procedure without
loading another procedural discovery/scoring document. Full-run and saved-job
launcher modes must work without the removed router. The scoring agent needs
only the three interactions and returned handles; internal private files may be
numerous without becoming caller obligations.

Run the existing meaningful regression cases through the consolidated public
interfaces. Retain evidence, frozen-requirement, resume-line, immutable-result,
unknown-submission and all-job failure tests. Compare equivalent saved workloads
before and after; show changes in loaded instructions and mechanical calls and
report real scoped timing. Reduced surface area alone is not proof of semantic
quality or a faster complete live run.

This design authorizes specification work only. Implementation cutover, necessary
live acceptance and normal production runs remain distinct scopes.
