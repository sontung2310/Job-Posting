# Proposal

## Why

The current job-fit score compares each job description only with two static
résumés. The user's verified career vault now contains richer, source-linked evidence,
so the pipeline should score actual demonstrated fit while still showing whether a
current résumé makes that fit visible.

## What Changes

- Add runtime retrieval of verified, source-linked career evidence from the local
  Obsidian Markdown vault.
- Add a transparent Candidate Evidence Fit score calculated from JD requirements
  and retrieved vault evidence; approved Obsidian application records will store
  this score in frontmatter.
- Retain a separate Resume Coverage assessment to choose the better of the two
  current résumés and expose evidence that is not yet represented in it.
- Require an auditable requirement-to-evidence scoring table and prevent jobs
  with unsupported mandatory requirements from qualifying for approval.
- Add vault preflight validation before paid discovery calls.

## Capabilities

### New Capabilities

- `vault-evidence-retrieval`: Validate and retrieve only eligible evidence from
  the local career vault, with source and verification traceability.
- `job-fit-scoring`: Calculate Candidate Evidence Fit and Resume Coverage from a
  normalized job description, enforce qualification rules, and report score
  evidence.

### Modified Capabilities

<!-- None. This project has no existing OpenSpec capability specifications. -->

## Impact

- Affected runtime: job-search preflight, daily-run prompt, and the scoring
  workflow instructions.
- New local tooling: a hybrid Python vault retrieval utility with literal keyword
  search and local semantic embeddings.
- Approved application records use the private Obsidian workspace: Candidate
  Evidence Fit, résumé coverage, and separate strengths, gaps, and suggested CV
  changes live in frontmatter and the source-linked body.
- No external tracker, Obsidian plugin, external retrieval service, or résumé
  mutation is added.
