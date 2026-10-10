# Consolidated assessment interface

## ADDED Requirements

### Requirement: Three agent-facing assessment interactions

The assessment helper SHALL expose preparation, condition/classification
submission and judgment/suggestion submission as its complete normal interaction
sequence. Helpers SHALL manage private filenames, fingerprints, ordering,
arithmetic and logs. Returned handles and generated decision templates SHALL
identify the required inputs without making Codex copy internal metadata or
invoke separate freeze, calculator and finalize commands. Existing mechanical
modules and private storage SHALL be reused.

#### Scenario: Assess saved jobs
- **WHEN** Codex starts job-scoring on a saved handoff
- **THEN** it prepares the jobs, submits conditions/classifications, and submits evidence judgments/suggestions
- **AND** it obtains validated outcomes and progress without coordinating internal artifact filenames

### Requirement: Prepare complete original inputs

Preparation SHALL validate or reuse current readiness and return full original
jobs, numbered JD units, a verified condition profile, every current extractable
resume's numbered text and saved discovery coverage. At least two extractable
resumes SHALL be required. Preparation SHALL NOT submit source searches or
require source credentials. Partial or unknown discovery coverage SHALL remain
partial or unknown.

#### Scenario: Complete empty handoff
- **WHEN** preparation receives an empty jobs list with complete discovery coverage
- **THEN** the run can complete with zero jobs without a fabricated assessment or a new search

#### Scenario: Partial discovery
- **WHEN** a saved handoff contains jobs and a failed source search
- **THEN** assessment can process supplied jobs while preserving incomplete discovery coverage

### Requirement: Conditions precede evidence retrieval

Codex SHALL interpret work-rights and explicitly required degrees from original
JDs and the verified profile. The helper SHALL validate supplied original clauses
and decision completeness without making semantic gate decisions. Known failures
SHALL produce condition-only outcomes and skip requirement retrieval and all
scores; failed jobs SHALL need no scoring classifications. Ambiguity SHALL
continue with a manual-review flag. Skills, licences and certifications SHALL
affect fit rather than independently gate jobs.

#### Scenario: Batch includes an ineligible job
- **WHEN** Codex submits a known failed condition alongside eligible jobs
- **THEN** the failed job receives no retrieval call or score
- **AND** eligible jobs continue through evidence retrieval

### Requirement: Freeze and retrieve accepted requirements internally

For eligible jobs, submission SHALL account for every original JD unit with a
reason and freeze full scored wording, category and priority before retrieval.
It SHALL use the existing batch retriever for every frozen requirement and
return inspectable verified claims, supporting source references and resume
line identifiers. Existing accepted requirements and saved retrieval SHALL be
reused on safe resume. Similarity SHALL retrieve candidates, never award points.

#### Scenario: Omitted original unit
- **WHEN** a submitted classification omits or duplicates a numbered JD unit
- **THEN** the helper rejects it before freezing or retrieval

### Requirement: Validate judgments against independent provenance

Judgment submission SHALL bind to independently persisted original inputs,
accepted conditions, frozen requirements and retrieval provenance. Every
requirement SHALL have a judgment and reason; positive Candidate Evidence Fit
SHALL cite current inspected verified claims and their sources. Positive Resume
Coverage SHALL have exact current supporting lines for every resume. Benefits,
education-only clauses and standalone keywords SHALL earn no points. Unsupported
seniority or compound scope SHALL NOT become direct evidence.

#### Scenario: Jointly edited review drops a frozen requirement
- **WHEN** a review changes classification and removes a frozen requirement from its judgments
- **THEN** independent persisted requirements cause validation failure rather than a lower score

#### Scenario: Forged resume support
- **WHEN** positive resume credit cites an absent line or supplies no lines
- **THEN** the affected job fails validation and no score is committed

### Requirement: Preserve scores, suggestions and all-job completion

The helper SHALL retain current category budgets, priorities, strength credit,
redistribution, rounding, resume tie-breaks and the configured exclusive
qualification threshold. Compatibility match JSON SHALL retain exactly category,
recommended_resume and ATS_score. Valid submission SHALL calculate and save
outcomes and privacy-safe condition/scoring/suggestion logs once per original
job. Every qualifier SHALL have concise sourced strengths, honest gaps, proposed
changes and manual-review wording before the report is complete.

Completion SHALL follow every original job having a validated outcome or explicit
failure, without a separately ordered manual finalization command. Malformed or
missing reviews SHALL be visible per-job failures and SHALL NOT prevent later
jobs from being accounted for. Coverage/time targets SHALL NOT omit jobs.

#### Scenario: Malformed first review
- **WHEN** a batch contains a malformed review followed by a valid review
- **THEN** the first job is an explicit failure and the second job is still validated
- **AND** the overall report cannot claim full successful assessment

#### Scenario: Exact threshold
- **WHEN** Candidate Evidence Fit equals the configured exclusive threshold
- **THEN** the job remains below threshold

### Requirement: Safe recovery and finalized immutability

Helpers SHALL durably preserve accepted work and reuse it without duplicate
records. Failed or missing work SHALL be repairable through the same public
interaction. Changed evidence/profile/resumes SHALL invalidate stale trust.
Finalized successful assessments SHALL remain immutable in their scoring run;
revised JDs, judgments or input provenance SHALL require a new scoring run so
logs and saved results remain consistent. Legacy saved handoffs SHALL be reused
or explicitly rejected for fresh scoring without hidden source submissions.

#### Scenario: Resume missing judgments
- **WHEN** valid work exists and some job reviews are missing
- **THEN** completed work is reused and the user can submit the missing reviews without restarting discovery

#### Scenario: Change a finalized assessment
- **WHEN** a previously finalized successful assessment is revised in place
- **THEN** the helper requires a new scoring run and preserves its existing result and log
