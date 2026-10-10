# Tasks

## 1. Vault retrieval and validation

- [x] 1.1 Replace the reviewed terminology map with OpenAI semantic retrieval and Chroma Cloud indexing; declare the embedding API dependency separately.
- [x] 1.2 Implement `scripts/vault_evidence.py check` to parse the supported Markdown frontmatter, reject ineligible notes, and verify failing prerequisites produce a non-zero exit and named reasons.
- [x] 1.3 Implement `scripts/vault_evidence.py search` to return ranked, traceable eligible note sections using literal and semantic signals; verify keyword, semantic-only, hybrid, and no-match fixture queries return the expected JSON candidates.
- [x] 1.4 Add unit fixtures and tests for frontmatter validation, section extraction, source/verification filtering, literal, semantic, and hybrid ranking, plus privacy-safe output; verify with `python3 -m unittest`.

## 2. Discovery safety and workflow contract

- [x] 2.1 Add vault validation to `scripts/run.sh --check` before the Codex discovery workflow can start; verify an invalid fixture prevents continuation and a valid fixture passes.
- [x] 2.2 Update the root instructions, Stage 1 workflow, and daily-run prompt to require vault validation and requirement-oriented evidence retrieval before scoring; verify the scheduled prompt cannot direct a paid search after failed preflight.
- [x] 2.3 Replace the Stage 2 scoring instructions with the Candidate Evidence Fit budget, priority allocation, direct/transferable/missing evidence rules, hard-requirement gate, and auditable table; verify a worked example totals 100 before rounding.

## 3. Resume coverage and approved-output behavior

- [x] 3.1 Update the scoring output contract so `ATS_score` represents Candidate Evidence Fit and `recommended_resume` is selected by separate per-résumé Resume Coverage; verify the candidate-facing JSON retains exactly its three keys.
- [x] 3.2 Update suggestion, Obsidian-write, and schema guidance to store
  Candidate Evidence Fit, Resume Coverage, and separate strengths, gaps, and
  suggested CV changes in approved application records; verify no workflow step
  edits a résumé or creates an external tracker record.
- [x] 3.3 Add scenario tests or documented acceptance examples for threshold equality, hard-gate exclusion, transferable evidence, résumé tie-breaking, and a vault-supported fact absent from the selected résumé.

## 4. End-to-end verification

- [x] 4.1 Run the full unit suite and `./scripts/run.sh --check`; verify the live vault passes and no private claim text is added to `logs/log.txt`.
- [x] 4.2 Run an approval-free discovery dry run against a representative retained JD; verify every awarded point cites eligible vault evidence, ineligible jobs remain outside the approval report, and a qualified result includes both scores.
- [x] 4.3 Run `openspec validate vault-based-job-fit-scoring --strict` and confirm all OpenSpec artifacts are complete before implementation begins.

## 5. Batch score observability

- [x] 5.1 Add a private scoring-ledger utility that hashes job URLs, records a short final score reason, consumes Codex JSON usage, and allocates the completed batch equally across scored JDs.
- [x] 5.2 Add the dated, source-linked rate card and scheduled-run prompt contract; keep zero-JD batches successful and detailed logs Git-ignored.
- [x] 5.3 Add unit coverage for token-cost calculation, equal-share allocation, privacy-safe output, and zero-JD completion; run the full verification suite.
