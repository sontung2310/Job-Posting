# Agent job search

## ADDED Requirements

### Requirement: Simple skill-led workflow

The project SHALL provide focused repository `job-retrieval` and `job-scoring`
skills and a short `job-search` entry point. Retrieval SHALL own preflight,
source calls, normalization, freshness, deduplication and discovery recovery.
Scoring SHALL own conditions, requirements, evidence assessment, validated scores,
suggestions and reporting. The entry point SHALL route between them without
duplicating phase instructions. Codex SHALL control the workflow; helpers SHALL
handle mechanical operations without direct model generation. Existing state
and utilities SHALL be reused. Files MAY be deleted, consolidated or reorganized
while preserving required behavior and private data.

#### Scenario: Run the workflow
- **WHEN** the workflow is invoked
- **THEN** Codex follows clear steps with completion criteria and loads references only as needed
- **AND** no custom workflow engine or generation API agent is required

### Requirement: Independent skills with a saved handoff

Both focused skills SHALL be independently invocable. Retrieval SHALL save
normalized full jobs, run/checkpoint reference, original cutoff and coverage
summary using existing private files. Scoring SHALL consume that snapshot without
source searches or job-source credentials, checking current evidence readiness
and reusing valid preflight work. A partial discovery SHALL remain visibly
partial in the final report. Retrieval-only output SHALL contain jobs and
coverage rather than assessed approval candidates.

#### Scenario: Score saved jobs
- **WHEN** job-scoring is invoked on an existing saved retrieval result
- **THEN** it validates evidence readiness and assesses the supplied jobs without submitting an Indeed or Apify search

#### Scenario: Retrieval-only invocation
- **WHEN** job-retrieval completes without job-scoring
- **THEN** it returns saved jobs and coverage without claiming fit scores or qualification

#### Scenario: Partial discovery handoff
- **WHEN** saved discovery contains valid jobs and a failed source search
- **THEN** scoring may assess those jobs but the final report preserves incomplete coverage

### Requirement: Complete coverage before runtime target

Every configured search SHALL be attempted and every retained job SHALL be
accounted for. Every eligible job SHALL be scored; no top-N quota or time-based
omission is allowed. The target SHALL be 10–15 minutes end to end. An overrun SHALL
be reported while useful authorized work continues. Source/result caps and
incomplete coverage SHALL be visible.

#### Scenario: Full current configuration
- **WHEN** the current six-title, six-city, three-source plan runs
- **THEN** all 108 combinations are attempted and successful completion requires all to succeed

#### Scenario: Target exceeded
- **WHEN** 15 minutes elapse with useful work remaining
- **THEN** Codex continues and reports the overrun rather than discarding jobs

#### Scenario: Source fails
- **WHEN** one search cannot complete
- **THEN** the report is explicitly partial or failed, never a successful empty result

### Requirement: Safe discovery and resume

Discovery SHALL use the configured Indeed plugin and LinkedIn/Seek Apify actors,
the fixed run-start 24-hour window, existing result caps and duplicate checks.
Helpers SHALL durably save responses and Actor IDs. Resume SHALL reuse confirmed
runs and completed work, without restarting unknown paid submissions. Generic
web search SHALL NOT replace a failed configured source.

#### Scenario: Interrupted paid submission
- **WHEN** a submission outcome is unknown
- **THEN** it remains blocked until reconciled rather than submitted again

#### Scenario: Existing application
- **WHEN** a normalized job duplicates an active or archived application
- **THEN** it is excluded before scoring

### Requirement: Report and approval boundaries

Every qualifier SHALL appear with job/source/date/URL, compatible match JSON,
resume coverage, sourced strengths, honest gaps, concise changes and ambiguous
conditions. Detailed tailoring SHALL happen during approved preparation. Initial
runs SHALL create no application records, resumes or cover letters. Approved
writes SHALL retain current duplicate checks, destination flags and separate
letter approvals. Applications, employer contact and resume edits remain prohibited.

#### Scenario: Complete run finds no qualifying jobs
- **WHEN** coverage and assessment are complete but no jobs qualify
- **THEN** the run succeeds plainly without requesting approval

#### Scenario: Candidate approved
- **WHEN** the user explicitly approves a candidate from the current report
- **THEN** only that candidate may be prepared at enabled destinations after repeated checks
- **AND** source resumes remain unchanged and cover-letter fields remain blank
