# Workflow instruction ownership

## ADDED Requirements

### Requirement: Exactly two substantive workflow skills

The active workflow SHALL expose job-retrieval and job-scoring as its only
job-search skills. The full-run launcher SHALL invoke retrieval followed by
scoring using the saved handoff. Saved-job mode SHALL invoke scoring alone.
The job-search router SHALL be removed at cutover, including active callers.

#### Scenario: Complete run
- **WHEN** the user starts a full job-search run
- **THEN** Codex executes job-retrieval and passes its saved jobs/coverage to job-scoring
- **AND** no third workflow skill is required

#### Scenario: Independent retrieval
- **WHEN** the user invokes job-retrieval alone
- **THEN** it returns private jobs and honest coverage without scores or approval candidates

#### Scenario: Independent scoring
- **WHEN** the user invokes job-scoring with saved jobs
- **THEN** it assesses them and presents results without submitting a job-source search
- **AND** source credentials are not required for assessment

### Requirement: One owner per procedure

Each skill SHALL contain the complete ordered procedure and completion criteria
for its phase. Retrieval SHALL own source discovery and its handoff. Scoring
SHALL own assessment and the final candidate report. Active reference documents
SHALL contain needed definitions, connector facts or contracts, not a competing
discovery/scoring procedure. Duplicated or obsolete procedures SHALL be retired
or consolidated and their active references updated together.

#### Scenario: Follow assessment instructions
- **WHEN** Codex follows job-scoring
- **THEN** the phase sequence is available in that skill
- **AND** references are loaded only for needed facts or contracts
- **AND** no numbered document supplies a second competing step sequence

### Requirement: Minimal global agent instructions

Global agent instructions SHALL contain a brief skill orientation and shared
verified-fact, privacy, approval, immutable-resume and unknown-paid-submission
guardrails. Phase commands, score formulas, reporting recipes and hard-coded
lookback durations SHALL belong to their responsible skill, helper, configuration
or reference. Simplification SHALL preserve the substance of the protections.

#### Scenario: Read global instructions
- **WHEN** Codex begins repository work
- **THEN** global instructions identify the two skills and shared protections
- **AND** they do not repeat the complete discovery or scoring procedure

### Requirement: Preserve approved preparation and private history

Initial retrieval/scoring SHALL create no application records, cover letters or
resume files. Destination schemas and preparation instructions SHALL load after
current-report explicit approval. Destination flags SHALL remain false by
default, duplicate/provenance checks SHALL repeat before approved writes, and
cover letters SHALL retain separate approval. Cleanup SHALL preserve private
evidence, resumes, packages and historical logs/reports.

#### Scenario: Qualifying candidate awaiting approval
- **WHEN** scoring reports a qualifying job
- **THEN** it presents concise sourced advice and waits for approval
- **AND** neither application submission nor preparation writes occur automatically

### Requirement: Shared readiness and honest completion

The launcher and independent skills SHALL reuse one readiness implementation
with mode-specific prerequisites and current-input fingerprint checks.
Unchanged valid readiness SHALL be reused; changed inputs SHALL be revalidated.
Every configured search and retained job SHALL be accounted for. Partial coverage
and failures SHALL remain visible; complete zero results SHALL succeed. Actual
timing and available usage SHALL retain honest scopes; unknown native usage SHALL
remain unavailable and required CLI completed-turn finalization SHALL remain.

#### Scenario: Scoring-only readiness
- **WHEN** saved jobs are assessed in keyword-only mode
- **THEN** readiness checks current local evidence/profile/resumes
- **AND** neither source authentication nor cloud initialization is required

#### Scenario: Reuse readiness from the launcher
- **WHEN** the invoked skill sees valid unchanged readiness from the launcher
- **THEN** it reuses that result instead of repeating the same mechanical preflight

### Requirement: Cleanup through replacement

Implementation SHALL migrate useful behavior to the consolidated interfaces and
retire their redundant active commands, wrappers and tests. It SHALL NOT add a
second workflow engine, generation API fallback or parallel instruction system.

#### Scenario: Consolidated helper replaces old commands
- **WHEN** the two skills have migrated to the smaller assessment interface
- **THEN** obsolete agent-facing entry points and their procedural recipes are removed
- **AND** existing meaningful behavioral checks remain protected
