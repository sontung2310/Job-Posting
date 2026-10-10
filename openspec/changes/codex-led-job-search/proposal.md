# Codex-led job search

## Why

The user wants Codex to run the job-search workflow and make its judgments,
with small helpers for mechanical work. Separate OpenAI generation API calls
are removed; embeddings remain allowed only when `hybrid_search: true`.

The target is 10–15 minutes. Full coverage takes priority: search every configured
combination and assess every retained job, even when the run takes longer.

## What Changes

- Add focused `job-retrieval` and `job-scoring` skills, with a short `job-search`
  entry point that routes between them without duplicating their instructions.
- Codex handles conditions, requirements, evidence judgments and suggestions.
- Reuse discovery checkpoints, retrieval, validation, score arithmetic and logs.
- Delete direct-generation code after preserving its useful local checks.
- Keep the launcher thin and load detailed instructions only when needed.
- Allow file deletion, consolidation and restructuring where they simplify the workflow.
- Check locally first; use one search on one platform for necessary live acceptance.

## Capabilities

### New Capabilities

- `agent-job-search`: simple skill-led workflow, full coverage, reports and approval.
- `codex-job-assessment`: evidence-grounded Codex judgments and validated scores.
- `job-search-runtime`: conditional embeddings, safe recovery and responsible testing.

### Modified Capabilities

None are archived in `openspec/specs/` at authoring time. At implementation cutover,
this change supersedes conflicting runner instructions and the older unarchived
proposal's obsolete scoring budgets and broad mandatory-skill gate.

## Impact

[design.md](design.md) contains the code disposition and success criteria.
[tasks.md](tasks.md) is the implementation checklist. Structure may be simplified
further without changing the required behavior.

This is a specification update, not implementation or authorization to run a
full paid crawl as a test. Resumes, career evidence and private history are preserved.

## Non-goals

A workflow engine, new MCP server, custom agent scheduler, generation API service,
automatic applications, employer contact, resume edits or initial destination writes.
