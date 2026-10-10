# Candidate report and selection

## ADDED Requirements

### Requirement: Four-part qualifier suggestions
After validated qualification, every qualifier SHALL contain JD priorities,
sourced strengths, honest gaps and a resume plan. Priorities SHALL reference
frozen requirements; strengths SHALL have verified citations; the plan SHALL
identify the recommended immutable resume and supported prioritized changes
labelled review before adding. Below-threshold jobs SHALL NOT require suggestions.

#### Scenario: Qualifying candidate
- **WHEN** a job scores above the configured threshold
- **THEN** its report displays all four suggestion sections and every resume's coverage
- **AND** suggestions preserve verified scope and metrics without changing the score

### Requirement: Complete private candidate report
The system SHALL persist a private report and numbered candidate mapping tied to
run/report identity and validated assessment provenance. Qualifiers SHALL appear
in descending fit order with deterministic ties. The report SHALL present job
identity, location, source/date/URL, advertised salary/contact when present,
match output, suggestions and original manual-review wording. It SHALL show
all assessment outcome counts, discovery coverage and concrete remaining failures.

#### Scenario: Partial discovery with completed assessment
- **WHEN** retained jobs are assessed but some configured searches failed
- **THEN** every qualifier is presented with partial discovery clearly identified
- **AND** the run is not described as complete source coverage or successful empty discovery

#### Scenario: Complete empty result
- **WHEN** discovery and assessment are complete with no qualifiers
- **THEN** the report records a successful empty candidate result without requesting candidate approval

### Requirement: Stable current-report selection
Candidate numbers SHALL remain stable within a report across redisplay/resume.
User selection SHALL resolve only against the current report's saved mapping.
Unknown or stale selections SHALL cause no destination writes.

#### Scenario: Accept two candidates
- **WHEN** the user says Accept 1 and 2 for the current report
- **THEN** only mapped candidates 1 and 2 enter approved preparation
- **AND** other qualifiers remain unapproved

#### Scenario: Stale or changed candidate
- **WHEN** selection references an old report or changed assessment provenance
- **THEN** the system requests a valid current selection or renewed review before any write

### Requirement: Flag-controlled approved destinations
Approved candidates SHALL write only to enabled destinations after renewed
eligibility, provenance and duplicate checks. Flags SHALL default to false and
selection SHALL NOT enable them. Each requested destination SHALL confirm its
own result. Source resumes SHALL remain immutable, application submission SHALL
remain prohibited, and cover letters SHALL require separate approval.

#### Scenario: Obsidian enabled and Notion disabled
- **WHEN** the user selects a current qualifying nonduplicate candidate with only Obsidian enabled
- **THEN** one verified Obsidian application record is created and confirmed
- **AND** Notion is skipped without a connector write
- **AND** no cover letter or application submission is created

#### Scenario: Both destinations disabled
- **WHEN** the user selects candidates with both destination flags false
- **THEN** both destinations are reported as skipped without writes

#### Scenario: Existing application record
- **WHEN** repeated destination checks find a duplicate
- **THEN** the existing record remains unchanged and the candidate is reported as skipped for that destination
