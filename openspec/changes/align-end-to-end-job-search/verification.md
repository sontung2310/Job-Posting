# Workflow implementation verification

## Implemented behavior

General job-search execution requests route through retrieval, scoring,
qualifier suggestions and the numbered report. Ordinary conversation does not
launch searches. The two skills retain their phase procedures; shared setup is
read once through AGENTS.md and stage-specific readiness stays with each skill.
Native scheduled prompts invoke the skills directly; run.sh remains the CLI
launcher. No automation was created.

The three references have purpose-based names and separated responsibilities.
Historical adapter citations resolve to the renamed reference; source changes
invalidate evidence fingerprints and repository symlinks cannot escape the
allowed source boundary.

Qualified score judgments now persist before suggestion authoring. Final
suggestions validate all frozen JD priorities, sourced strengths, requirement-linked
gaps and the recommended resume plan with supported review-before-adding changes.
All original jobs remain accounted for. Incomplete reports are visible and
nonselectable; final report IDs/numbers and bytes remain stable. Selection checks
current report identity, completed outcomes, evidence/resume provenance, cached
outcome integrity and the frozen/current configured threshold. Destination flags
remain disabled by default and writes remain in approved skill preparation.

## Automated checks

- 111 tests passed using the existing local unittest suite, including the public
  assessment/scoring, discovery, readiness, saved handoff and launcher seams.
- Added actual arithmetic cases for fit 74, 75 and 76: the configured exclusive
  threshold rejects the first two and qualifies 76.
- Added checks for score-first suggestions, required report metadata, stable
  multi-candidate numbering, incomplete-report rejection, altered saved-result
  rejection, threshold changes, selected candidate mapping, destination flag
  types, source resume immutability and legacy reference resolution.
- Launcher fixture verifies external child-process artifacts are private (600)
  and the report directory is private (700). Bash syntax and git diff checks pass.
- Strict OpenSpec validation passes.

Tests use synthetic PDFs and saved connector fixtures. The bundled Poppler
pdftotext executable supplies the local PDF boundary. Embedding/cloud failure
checks substitute the external service boundary; they perform no paid operations.

## Agent acceptance with saved fixtures

An agent-authored native scheduled fixture prompt was replayed against a saved
four-job handoff. The saved discovery boundary contained 108 synthetic search
outcomes with partial coverage (102 complete). Scoring used local keyword mode,
inspected verified synthetic evidence and the exact current resume lines, and
continued directly through the report without a nested CLI agent.

| Outcome | Count |
| --- | ---: |
| Original jobs | 4 |
| Known citizenship condition failure | 1 |
| Below threshold (fit 50) | 1 |
| Qualified (fit 100) | 2 |
| Unresolved jobs after completion | 0 |

One qualifier retained its original ambiguous permanent-work-rights clause.
Both qualifiers received all four suggestion sections. Redisplay preserved the
report ID and candidate numbers. Stale/unknown selections were rejected;
default destination flags produced no application writes. Source PDF hashes
remained unchanged and report files were mode 600.

A fixture-only selection of candidate 1 was then followed through the approved
preparation instructions. Only its temporary Obsidian record was created; the
other candidate had no record. Repeated approval detected the existing local
record and left it unchanged. A mocked Notion query returned an existing URL and
was treated as a duplicate without a write. No real destinations, cover letters,
applications or employers were touched.

## Measured payload change

For the same four-job fixture and representative 108-search coverage, a one-job
inspect response fell from 17,184 bytes to 1,113 bytes (93.5% reduction). The
post-change path loaded shared inputs once, then referenced them by handle. The
complete fixture scoring/report path took approximately 0.76 seconds; this is
local fixture timing, not a production runtime or model-token benchmark.
Source searches, cloud calls and nested Codex processes during acceptance: zero.

## Review and limits

Spec review found missing report metadata, report suppression on failures and
missing acceptance coverage. Those findings were fixed; re-review found no
remaining blocking spec findings. Standards/correctness review also led to cached
outcome integrity, frozen threshold and CLI report-permission fixes. The second
independent standards-agent dispatch hit the collaboration service thread limit;
the parent reviewed that axis directly.

Native automation dispatch and live Notion creation/confirmation were not
exercised. The fixture checks validate the instruction and handoff contract, not
a deployed schedule or live connector access. No new source discovery was needed.

Legacy finalized scoring files without threshold/integrity metadata require a
new scoring run from the saved handoff rather than silent cache reuse. Historical
state and reports stay intact; existing source Actor IDs and discovery windows
are not restarted. Existing uncertain paid-work markers still require explicit
reconciliation/approval before another paid operation.
