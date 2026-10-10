# Selected-job suggestions

## ADDED Requirements

### Requirement: Scoring ends at the ranked report
The scoring skill SHALL check conditions, retrieve verified evidence, calculate
fit and every current resume's coverage, and present a stable ranked report.
Qualified outcomes SHALL finalize without detailed suggestions. Scoring SHALL
NOT generate suggestions or perform destination preparation.

#### Scenario: Qualifying score before selection
- **WHEN** a job qualifies and all scoring outcomes are resolved
- **THEN** the ranked report is selectable without any suggestion artifact
- **AND** no suggestion logs or destination records are created

### Requirement: Selected-only suggestion skill
AGENTS.md SHALL route explicit current-report selections through a separate
selection helper to job-suggestions. The helper SHALL validate report identity,
completion, configured threshold and current provenance before saving a private
selection handle. Suggestion submissions SHALL be limited to that approved set.

#### Scenario: Choose one of two qualifiers
- **WHEN** the user selects candidate 2 from the current report
- **THEN** only candidate 2 receives JD priorities, sourced strengths, honest gaps and a resume plan
- **AND** candidate 1 cannot be added through the suggestion submission
- **AND** scores and source resumes remain unchanged

### Requirement: Destination preparation has its own owner
AGENTS.md SHALL load approved-destination-writes and application-package-reference
only after selected-job suggestions are ready. Those documents SHALL own the
write procedure and record contents. Enabled flags, repeated duplicate/provenance
checks, independent confirmation and separate cover-letter approval SHALL remain.

#### Scenario: Disabled destinations
- **WHEN** a user selects a job but both destination flags are false
- **THEN** suggestions can be presented and both destinations remain skipped

### Requirement: Resources follow stage ownership
Exclusive stage scripts and references SHALL live within their skill directories.
Shared evidence, readiness, validation, logging and private-I/O utilities SHALL
remain shared. Active callers and tests SHALL use the new paths; historical
artifacts SHALL remain intact.

#### Scenario: Run the relocated scoring entry point
- **WHEN** the skill invokes its local assessment script from the project root
- **THEN** it resolves shared helpers and configuration from the repository root
- **AND** its selection command is supplied by the separate preparation entry point
