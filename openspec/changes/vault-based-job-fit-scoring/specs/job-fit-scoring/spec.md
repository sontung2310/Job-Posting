# Spec Delta

## Purpose

Calculate a transparent job-fit result from verified career-vault evidence while
separately showing how well each current résumé communicates that evidence.

## ADDED Requirements

### Requirement: Candidate Evidence Fit budget

The system SHALL calculate Candidate Evidence Fit on a 0–100 scale using these
base category budgets: explicit must-have skills 35, responsibilities and
demonstrated experience 25, domain/tool alignment 15, seniority and scope 10,
education/certification 5, and contextual keyword coverage 10. It SHALL divide
each present category budget across that category's JD requirements according to
their normalized priority. If a whole category is absent from the JD, the system
SHALL redistribute its budget proportionally across present categories so the
available total remains 100.

#### Scenario: All categories are present
- **WHEN** a JD contains requirements for all six categories
- **THEN** the total available score is exactly 100 using the base category budgets

#### Scenario: Education is absent
- **WHEN** a JD contains no education or certification requirement
- **THEN** its 5 points are redistributed proportionally and the total available
  score remains exactly 100

### Requirement: Evidence-grounded requirement scoring

For every scored JD requirement, the system SHALL record the allocated points,
supporting vault evidence, evidence strength, earned points, and any gap. Direct,
verified evidence SHALL earn all allocated points; clearly documented transferable
evidence SHALL earn half; missing, vague, or unverified evidence SHALL earn zero.
The final Candidate Evidence Fit score SHALL be rounded to the nearest integer.

#### Scenario: Direct evidence fulfills a requirement
- **WHEN** an eligible evidence note explicitly demonstrates a required skill or
  responsibility
- **THEN** that requirement earns its full allocated points and cites the note

#### Scenario: Transferable evidence is partial credit
- **WHEN** eligible evidence demonstrates a closely transferable capability but
  not the stated requirement itself
- **THEN** that requirement earns half of its allocated points and is labelled
  transferable

#### Scenario: Search result lacks supporting proof
- **WHEN** retrieval returns a candidate note that does not substantiate the JD
  requirement
- **THEN** the requirement earns zero points and is recorded as a gap

### Requirement: Mandatory-requirement eligibility gate

The system SHALL identify requirements explicitly stated as mandatory, required,
or application eligibility conditions, including work authorisation, licences,
and required qualifications. A job with any such requirement unsupported by
eligible vault evidence SHALL be ineligible, regardless of its raw Candidate
Evidence Fit score, and SHALL NOT enter the approval report or suggestion stage.

#### Scenario: High score with an unsupported mandatory licence
- **WHEN** a job has a raw score above the configured threshold but its mandatory
  licence has no eligible supporting evidence
- **THEN** the job is reported as ineligible and is excluded from approval

#### Scenario: Preferred skill is absent
- **WHEN** a preferred but non-mandatory skill lacks evidence
- **THEN** it reduces the score without making the job ineligible

### Requirement: Separate Resume Coverage assessment

The system SHALL assess each current résumé against the same JD requirements and
produce a separate 0–100 Resume Coverage score for each. It SHALL select the
résumé with the higher coverage as `recommended_resume`; a tie SHALL be resolved
by coverage of the highest-weight mandatory requirements. Resume Coverage SHALL
be reported as a readiness signal and SHALL NOT change eligibility.

#### Scenario: Vault fit exceeds résumé visibility
- **WHEN** verified vault evidence supports a requirement that the selected résumé
  does not show
- **THEN** Candidate Evidence Fit receives the applicable vault points and Resume
  Coverage exposes the omission without disqualifying the job

#### Scenario: Résumé tie
- **WHEN** both résumés have the same Resume Coverage score
- **THEN** the system selects the résumé covering more high-weight mandatory
  requirements

### Requirement: Qualification and compatible result reporting

The system SHALL qualify a job only when Candidate Evidence Fit is strictly
greater than the configured exclusive threshold and no mandatory-requirement gate
has failed. The candidate-facing match JSON SHALL retain exactly `category`,
`recommended_resume`, and `ATS_score`; `ATS_score` SHALL contain Candidate
Evidence Fit. The system SHALL report Resume Coverage and the full scoring table
outside that three-key JSON.

#### Scenario: Score equals the exclusive threshold
- **WHEN** Candidate Evidence Fit equals 75 and the configured threshold is
  greater than 75
- **THEN** the job does not qualify for approval

#### Scenario: Qualified job is prepared for approval
- **WHEN** Candidate Evidence Fit exceeds the threshold and every mandatory
  requirement is supported
- **THEN** the approval report includes the three-key match JSON, Resume Coverage,
  and the traceable scoring table

### Requirement: Private batch scoring observability

For each JD that reaches Stage 2, the system SHALL retain a private score record
containing the rounded Candidate Evidence Fit, status, and a short factual reason.
After the single scoring batch finishes, it SHALL retain the batch elapsed time,
the exposed Codex token usage, and a token-cost estimate, and SHALL allocate each
total equally across its scored JDs. The detailed ledger SHALL be Git-ignored and
SHALL NOT contain a full JD, raw job URL, or vault evidence text. A batch with no
scored JDs SHALL remain successful and retain only its batch summary.

#### Scenario: Two JDs complete in one batch
- **WHEN** two JDs reach Stage 2 during one Codex scoring run
- **THEN** each private JD record contains half of the batch time, token, and
  token-cost estimate, clearly identified as an equal-share allocation

#### Scenario: No JD reaches Stage 2
- **WHEN** discovery produces no retained JDs to score
- **THEN** the run succeeds, a zero-count batch summary is retained, and no
  undefined per-JD allocation is written

### Requirement: Obsidian application record and suggestion evidence handling

After explicit approval, the system SHALL create one private Obsidian application
record for each approved, non-duplicate candidate. Its frontmatter SHALL store
Candidate Evidence Fit, both résumé coverage scores, separate concise strengths,
gaps, suggested CV changes, the selected résumé, and a blank user-owned
cover-letter field. The Markdown body SHALL store the normalized JD and expanded
source-linked evidence. There SHALL be no tracker `category` column. Suggestions
SHALL cite only verified, source-linked vault evidence or the selected résumé,
SHALL identify vault evidence absent from the résumé as material to review, and
SHALL NOT modify either résumé.

#### Scenario: Approved qualified job is saved
- **WHEN** a qualified job receives explicit user approval and passes the repeat
  duplicate check
- **THEN** the Obsidian application record contains Candidate Evidence Fit,
  separate coverage and evidence details, and a blank cover-letter field
