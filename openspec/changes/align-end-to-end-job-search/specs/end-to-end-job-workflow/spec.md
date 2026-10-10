# End-to-end job workflow

## ADDED Requirements

### Requirement: Default full-pipeline routing
The system SHALL start the pipeline only for an explicit job-search execution
request or an authorized scheduled task trigger. It SHALL route fresh-job
execution requests through discovery, condition
checks, evidence scoring, qualifier suggestions and a human-selection report.
AGENTS.md SHALL identify the exact paths of the two skills and the ordered
handoff. Explicit retrieval-only and saved-job scoring SHALL retain their scope.

#### Scenario: Fresh jobs requested in chat
- **WHEN** the user requests fresh jobs from the latest 24 hours
- **THEN** retrieval passes its saved jobs and coverage directly to scoring
- **AND** execution continues through the candidate report without another user prompt
- **AND** application records await current-report selection and enabled flags

#### Scenario: Explicit alternate scope
- **WHEN** the user requests only retrieval or scoring of saved jobs
- **THEN** only that requested phase executes
- **AND** scoring-only performs no source discovery

#### Scenario: Ordinary conversation
- **WHEN** the user asks a question about the workflow, requests specification changes or discusses code
- **THEN** the system handles that request without starting discovery or scoring

### Requirement: Native scheduled and CLI entry points
The system SHALL retain run.sh for terminal-based execution. Native scheduled
tasks SHALL invoke the local project's workflow through its instructions and
skills directly, without launching another Codex process through run.sh. Manual
and scheduled runs SHALL share phase contracts and candidate-report completion
criteria. Schedule creation SHALL require a separate explicit user request.

#### Scenario: Authorized morning run
- **WHEN** an explicitly configured morning task triggers in Australia/Melbourne time
- **THEN** it executes the requested lookback through the candidate report using the two skills
- **AND** it does not implicitly approve candidates or write application records
- **AND** it does not spawn a nested CLI Codex run

#### Scenario: Implement scheduling support
- **WHEN** this workflow change is implemented without a separate scheduling request
- **THEN** no automation is created and no execution time is assumed
- **AND** local scheduling prerequisites and a durable example prompt are documented

### Requirement: Single instruction ownership
The system SHALL retain exactly two workflow skills. AGENTS.md SHALL own routing,
shared protections and approval rules. Each skill SHALL own its phase procedure
and prerequisites. References SHALL supply branch-specific details without
competing discovery/scoring procedures.

#### Scenario: Retrieval prerequisites
- **WHEN** retrieval runs independently
- **THEN** scoring PDF and embedding prerequisites do not block discovery
- **AND** shared evidence/privacy protections still apply

### Requirement: Continue to meaningful completion
Every retained original job SHALL have a validated outcome or an explicit
failure/blocker. A checkpoint or bounded batch SHALL NOT itself complete a full
run. Partial discovery SHALL remain visible while retained jobs are assessed.

#### Scenario: Resume an interrupted assessment
- **WHEN** a run has accepted condition reviews and unresolved jobs
- **THEN** execution reuses accepted work and continues with unresolved jobs
- **AND** it reports remaining counts and a resume point if a concrete blocker stops progress

### Requirement: Condition-first scoring and exclusive qualification
Known failed work-rights or required-degree conditions SHALL stop scoring for that
job before requirement evidence retrieval. Passed or unclear conditions SHALL
proceed with verified evidence retrieval and semantic assessment. Qualification
SHALL use the configured exclusive threshold, independently of resume coverage.

#### Scenario: Ambiguous condition
- **WHEN** a condition cannot be resolved from verified profile facts
- **THEN** scoring proceeds with exact original wording flagged for manual review

#### Scenario: Current threshold boundary
- **WHEN** the configured exclusive threshold is 75
- **THEN** scores 74 and 75 are below threshold and 76 qualifies

### Requirement: Efficient bounded assessment
Assessment responses SHALL reference unchanged shared inputs and full private
coverage rather than repeatedly emit them. Full JDs, supporting sources and
complete original-unit accounting SHALL remain available and verified.

#### Scenario: Inspect another job
- **WHEN** the same run advances to another job
- **THEN** the response supplies job-specific working material and compact progress
- **AND** shared profile, resume and coverage material remains inspectable by handle

### Requirement: Purpose-named references
Active references SHALL use approved-destination-writes.md,
application-package-reference.md and additional-source-adapters.md. The first
SHALL own destination operations; the second SHALL define package contents; the
third SHALL describe optional source adapters. Migration SHALL preserve verified
historical citations, private data and existing records.

#### Scenario: Normal discovery
- **WHEN** the configured Seek, LinkedIn and Indeed queries execute
- **THEN** optional-adapter and approved-destination instructions are not loaded as normal discovery steps

#### Scenario: Repository-source migration
- **WHEN** a renamed document supports a verified evidence citation
- **THEN** its active reference is revalidated or a verified legacy resolution is preserved
- **AND** historical evidence is not silently discarded
