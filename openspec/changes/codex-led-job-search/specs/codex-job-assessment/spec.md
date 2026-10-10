# Codex job assessment

## ADDED Requirements

### Requirement: Codex owns semantic judgments

Codex SHALL inspect the complete JD, verified condition profile and retrieved
sources. Known explicit work-rights or required-degree mismatches SHALL fail
before retrieval/scoring. Ambiguity SHALL continue with manual review. Missing
skills/licences/certifications SHALL affect scores, not independently gate jobs.
Code MAY surface clauses but SHALL NOT make final semantic decisions.
These responsibilities SHALL belong to `job-scoring`, which consumes saved jobs;
career-vault evidence retrieval is part of scoring, not job-source discovery.

#### Scenario: Known degree mismatch
- **WHEN** an explicit required degree conflicts with verified profile facts
- **THEN** only a failed condition is recorded, without retrieval or scores

#### Scenario: Ambiguous condition
- **WHEN** a condition cannot be decided from the available wording/evidence
- **THEN** scoring continues and the report flags the original wording

### Requirement: Complete evidence assessment

Every original JD unit SHALL be classified with a reason; every scored requirement
SHALL preserve original wording and be retrieved through existing batch retrieval.
Codex SHALL inspect verified claims and supporting sources before assigning direct,
transferable or missing strength. Benefits, education-only clauses and keyword or
semantic similarity SHALL earn no standalone points. Seniority and compound scope
SHALL remain part of the assessment.

#### Scenario: Similar text without proof
- **WHEN** a retrieval hit does not demonstrate the requested scope
- **THEN** similarity alone earns no points

#### Scenario: Omitted requirement
- **WHEN** a numbered JD unit or frozen requirement is missing or duplicated
- **THEN** local validation rejects the result before scoring

### Requirement: Validated fit and resume coverage

Helpers SHALL validate current verified citations, exact requirement IDs and
positive supporting resume-line IDs before calculating fit and every resume's
coverage. At least two extractable resumes SHALL be required. Fit/coverage SHALL
retain 35/35/30 category budgets, priority weights 3/2/1, credit 100%/50%/0%, absent
category redistribution, half-up rounding and existing resume tie-breaks.
Qualification SHALL require fit above the configured exclusive threshold (75
currently) with no known failed condition. Match JSON SHALL retain exactly
category, recommended_resume and ATS_score, with ATS_score meaning Candidate
Evidence Fit.

#### Scenario: Forged resume line
- **WHEN** a positive resume judgment cites an absent line or no lines
- **THEN** validation rejects it and no score is committed

#### Scenario: Exactly threshold fit
- **WHEN** fit equals the current threshold of 75
- **THEN** the job is below threshold

#### Scenario: Verified fact absent from resume
- **WHEN** vault evidence supports a fact absent from the selected resume
- **THEN** fit and coverage differ appropriately and proposed additions are labelled review before adding

### Requirement: Complete private results

Each original job SHALL have its own validated outcome or explicit failure, even
when identical JDs share calculations. Full classifications, evidence tables and
resume support SHALL remain private. Unresolved invalid output SHALL be a failure,
not a low score. Native workers MAY assess disjoint groups when useful; one agent
SHALL be sufficient to run the full workflow without a custom scheduler.

#### Scenario: Worker fails validation
- **WHEN** assessment cannot produce supported complete judgments
- **THEN** that job remains a visible failure and the run cannot claim full completion
