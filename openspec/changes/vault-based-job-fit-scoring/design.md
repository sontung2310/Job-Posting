# Design

## Context

The existing project is an instruction-driven Codex workflow with shell
preflight scripts; it has no application service or package-managed runtime.
The local `career-vault/` contains Obsidian Markdown, and the root workflow
currently scores two résumé PDFs directly. See [proposal.md](proposal.md) for
the change motivation and the two capability specs for required behavior.

## Goals / Non-Goals

**Goals:**

- Make verified Obsidian evidence available to every retained JD in a repeatable,
  source-traceable form.
- Enforce the vault readiness gate before paid searches.
- Make the score auditable in private Obsidian application records.
- Preserve résumé selection and truthfulness safeguards.

**Non-Goals:**

- Building an Obsidian plugin, persistent vector database, or external retrieval
  service.
- Editing, promoting, or creating career-vault notes automatically.
- Automatically rewriting or applying a résumé.

## Decisions

### Runtime Markdown retrieval

Add a Python utility at `scripts/vault_evidence.py`. Its `check` command
validates vault readiness; its `search` command accepts a full JD requirement and
optional literal terms, then returns matching evidence sections as JSON. It reads
the vault fresh on each invocation and does not create a persistent index.

This fits the small, local vault and avoids plugin configuration and data-sync
risks. A generated JSON or SQLite index was rejected because it adds refresh and
privacy failure modes without a current scale benefit. An Obsidian connector was
rejected because the vault is already available as local Markdown.

### Narrow, safe note contract

The utility will parse the vault's established YAML-frontmatter subset (`type`,
`status`, `source`, `last_verified`, and `skills`) and Markdown headings. A note
with malformed frontmatter or incomplete verification metadata is not eligible
and is reported by `check`; it is never interpreted optimistically. The parser
will not write vault files.

`hybrid_search` selects the retrieval mode. When true, the explicit
`scripts/index_vault_chroma.py` sends each eligible section to OpenAI's
`text-embedding-3-small` API and stores its vector, citation metadata, and a
fingerprint of eligible indexing inputs in Chroma Cloud. Scoring sends each JD
requirement to OpenAI for query embedding, then sends that vector to Chroma for
comparison. Chroma stores no source text. Hybrid preflight sends the fixed text
`preflight` to OpenAI to verify embedding access before paid discovery.
When false, the utility does keyword retrieval only and does not call OpenAI or
connect to Chroma.

There is no project-controlled terminology map. The Codex workflow supplies the
full JD requirement and may add exact JD terms (such as an acronym or product
name) at query time. The hybrid score orders candidates only. Returned candidates
are not proof: the Codex scoring workflow must inspect the claim before assigning
an evidence strength.

### Hybrid retrieval, agent-led evidence judgement

The utility owns deterministic validation, filtering, configurable retrieval, and
traceable candidate output. The Codex workflow owns JD requirement extraction,
contextual choice of literal terms, priority allocation, evaluation of direct
versus transferable evidence, and the final scoring table. This lets the LLM use
the JD's meaning without allowing either a keyword or an embedding score to
become a factual claim.

The revised Stage 2 instructions will define the 100-point calculation, the
50-percent transferable-evidence rule, requirement allocation, hard-gate logic,
and report format. The agent will query the utility for every requirement and
will record the exact selected evidence path and section.

### Pipeline and compatibility

`scripts/run.sh --check` will call vault validation before a manual Codex
discovery workflow can start. The native Codex scheduled task reads the same root
instructions and runs that preflight itself. Root instructions and Stages 1–4
will use Candidate Evidence Fit as the eligibility score, then separately assess
both PDFs for Resume Coverage and `recommended_resume`.

The approved Obsidian application record is the integration boundary. Its
frontmatter receives the rounded Candidate Evidence Fit, both résumé coverage
scores, separate concise strengths, gaps, and suggested CV changes, the selected
résumé, and a blank user-owned cover-letter field. The Markdown body retains the
normalized JD and complete source-linked evidence detail.

### Equal-share batch scoring ledger

An explicit CLI runner executes one Codex scoring batch rather than one model
turn per JD. The prompt supplies a run ID and requires the agent to record the
final Stage 2 result for every scored JD through `scripts/scoring_ledger.py`.
The utility hashes the canonical URL, retains only the company, position, score,
status, and short reason in a private staging file, and rejects duplicate draft
records.

The CLI runner invokes `codex exec --json` and pipes its event stream to the
utility after the turn. The utility takes the final `turn.completed` usage
object, calculates a dated, source-linked token-cost estimate from the configured
model rate card, measures wall-clock batch duration, and divides all totals
equally by the count of recorded JDs. Its permanent JSONL log is Git-ignored.
This meets the need for per-JD operational estimates without creating a separate
paid model run or attempting unreliable inference-level attribution. If no JD is
scored, the batch summary is retained without an allocation. Native Codex
scheduled tasks do not expose this event to the task, so their task result records
scores and short reasons but intentionally omits token and cost estimates.

## Risks / Trade-offs

- [A required fact is missing from the vault] → Preflight and hard gates stop a
  false-positive recommendation; the report explains the missing requirement.
- [Lexical search misses differently worded evidence] → Combine literal matches
  with Chroma Cloud vector retrieval when `hybrid_search` is enabled; inspect
  project, experience, and evidence candidates before deciding a gap.
- [Semantic search overstates related experience] → Treat all retrieval output as
  a candidate; require cited, verified text before classifying it as direct or
  transferable, and never let semantic similarity satisfy a hard requirement.
- [A valid vault claim is absent from the chosen résumé] → Keep Resume Coverage
  separate and surface it as a truthful review item, not an automatic claim.
- [Personal evidence leaks into operational logs] → Keep logs aggregate-only;
  return evidence only to the active scoring context and approved private
  Obsidian record.
- [Batch estimates are mistaken for exact JD metering] → Mark every allocation
  as an equal-share batch estimate and retain the batch total alongside it.
- [Vault structure evolves beyond the supported frontmatter subset] → Fail closed
  for affected notes and extend the parser with test fixtures before relying on
  the new structure.

## Migration Plan

1. Add the hybrid retrieval utility, its OpenAI embedding dependency, and unit
   fixtures/tests.
2. Update preflight scripts and workflow instructions together, including the
   daily-run prompt and Obsidian-record guidance.
3. Run vault validation and a dry scoring pass against representative JDs; verify
   that every awarded point has an eligible note and source trace.
4. Enable the revised scheduled workflow only after the preflight succeeds.

No external data migration is needed. Rollback consists of restoring the prior
scoring instructions and removing the vault preflight call; private Obsidian
records remain local application history.
