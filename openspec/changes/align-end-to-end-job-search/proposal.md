# Align the end-to-end job-search workflow

## Why

A request to get fresh jobs currently reaches the retrieval-only skill and ends
with a saved handoff. The CLI launcher chains retrieval and scoring, but chat
routing does not clearly require the same behavior. The recent run retained 198
jobs, then the separate scoring request stopped after two condition reviews with
no completed scores or candidate report. A saved checkpoint is being treated as
a satisfactory stopping point instead of an intermediate artifact.

The user expects discovery → conditions and evidence scoring → suggestions for
qualifiers → numbered human selection → writes to enabled destinations. Numbered
docs, overlapping instructions, large repeated assessment payloads and an
incomplete suggestion/report contract make that workflow harder to execute.

## What Changes

- Make explicit job-search execution requests run retrieval and scoring through
  a candidate report; ordinary discussion never launches the pipeline. Preserve
  explicit retrieval-only and saved-job modes.
- Support the same workflow through native scheduled prompts and the existing
  CLI launcher, without nesting a CLI Codex process inside a native task.
  Creating an actual schedule remains a separate user request.
- Keep exactly two skills. Put routing and shared protections in AGENTS.md;
  keep stage procedures and mode-specific readiness in the responsible skill.
- Rename and consolidate destination/package/source-adapter reference docs.
- Reduce repeated assessment payloads without weakening full-JD inspection,
  evidence verification or accounting for every retained job.
- Define four suggestion outputs: JD priorities, sourced strengths, honest gaps
  and a resume plan. Generate them for scores above the configured threshold.
- Save and present a numbered candidate report with a durable approval mapping,
  explicit progress, coverage and resumable blockers.
- Resolve selected candidates from the current report and write only to enabled
  destinations after repeated duplicate/provenance checks.

## Impact

Affected areas: global instructions, the two skills, README and scripts map,
assessment helper/templates/results, launcher/report handoff, destination
references, evidence-source path resolution, and fixture-based checks.

This change supersedes earlier instruction-ownership decisions where they omit
chat routing or conflict with the ownership described here. Existing score
budgets, configured threshold, source selection, configurable lookback, privacy,
source-resume immutability and uncertain-paid-operation protections remain.

## Out of Scope

No third skill, workflow engine, direct generation API, new job sources,
automatic applications, employer contact, source-resume edits, initial
application writes or automatic cover letters. No new live retrieval or paid
benchmark is required to implement or validate this change. Existing private
handoffs, evidence and history must be preserved.
