## ADDED Requirements

### Requirement: Direct provider lookback and honest precision
New discovery acquisitions SHALL use the selected lookback at submission time,
defaulting to 24 hours, without expanding it for queue delays. Each acquisition
SHALL persist its interval, actual filter and posting-date precision. Exact
outside-window dates SHALL be rejected. Uncertain provider-filtered jobs MAY be
assessed with visible uncertainty but SHALL NOT be labelled confirmed fresh.

#### Scenario: Delayed Seek request
- **WHEN** a 24-hour Seek request is submitted after initialization or resume
- **THEN** dateRange is 1, not 2, and its own submission interval is recorded

#### Scenario: LinkedIn calendar date
- **WHEN** a job has only a calendar date and a recorded supported 24-hour filter
- **THEN** it is assessed as provider-filtered with uncertain time unless its date interval proves freshness or exclusion
- **AND** no exact timestamp is fabricated

#### Scenario: Unsupported date filter or contradictory date
- **WHEN** a provider lacks a supported requested filter or returns a provably older job
- **THEN** the limitation or exclusion is recorded explicitly
- **AND** a provider filter cannot override the contradictory date

#### Scenario: Longer lookback and legacy resume
- **WHEN** a user requests 48 hours or resumes a legacy fixed-window run
- **THEN** new 48-hour requests use a supported covering filter with precision reporting
- **AND** the legacy interval and historical records remain unchanged

### Requirement: Progressive round-robin assessment
The coordinator SHALL acquire and assess bounded batches in Seek, LinkedIn,
Indeed order, skipping unavailable sources with visible reasons. It SHALL stop
at five unique eligible jobs, 100 unique jobs admitted to gate assessment, budget
exhaustion, or source exhaustion. Eligibility SHALL retain existing scoring/gate
rules. Pending jobs SHALL be saved without automatic suggestions or writes.

#### Scenario: Fifth eligible job in a batch
- **WHEN** the fifth eligible job is found partway through a batch
- **THEN** no further job is assessed or source submitted automatically
- **AND** unconsumed jobs are preserved and a selectable ranked report is returned

#### Scenario: Assessment limit and unavailable source
- **WHEN** 100 unique jobs have entered gate assessment, including condition failures
- **THEN** assessment stops even if fewer than five qualify
- **AND** duplicates and retrieval rejections have not inflated that count
- **AND** an unavailable LinkedIn source did not prevent Seek and Indeed assessment

### Requirement: Relevance-based source stopping
Retrieval SHALL evaluate relevance from role title and duties separately from fit,
persist its judgments and apply configurable consecutive-batch stopping criteria.
It SHALL NOT use a fixed result position or candidate score as an irrelevance
cutoff. Query stops SHALL NOT silently suppress unrelated queries.

#### Scenario: Low-relevance streak
- **WHEN** two consecutive full evaluable batches have relevance below the configured threshold
- **THEN** that query stops before further acquisition and reports the heuristic reason
- **AND** other queries/platforms continue until their own or session limits

#### Scenario: Uncertain, duplicate or isolated irrelevant roles
- **WHEN** relevance is uncertain, duplicates dominate, or one unrelated job occurs
- **THEN** those facts are separately recorded and do not alone establish an irrelevance streak

### Requirement: Scraping control and budget reservation
Before paid acquisition the runner SHALL verify supported caps/continuation and
reserve maximum applicable event costs within the session allowance. Dataset
read pagination SHALL NOT be represented as avoided acquisition cost. Default
allowance SHALL be USD 0.50 and optional salary enrichment SHALL be disabled.

#### Scenario: Actor has no verified continuation
- **WHEN** a capped query has been scraped and no nonrepeat continuation is verified
- **THEN** its saved results are consumed and coverage is marked capped/noncontinuable
- **AND** no larger-cap prefix rerun is submitted

#### Scenario: Budget or unknown submission
- **WHEN** the next capped submission would exceed the allowance or an earlier submission is unknown
- **THEN** no unauthorized additional paid request occurs
- **AND** the reservation and stopping/reconciliation reason remain durable on resume

### Requirement: Compatible saved-data reuse
The workflow SHALL consume compatible downloaded jobs before repeating searches,
deduplicate before assessment and reuse successful assessments only with matching
input/policy fingerprints. Reuse SHALL preserve provenance and validate current
freshness rather than silently relabel historical jobs as fresh.

#### Scenario: Resume in another output directory
- **WHEN** the same session continues using another output directory
- **THEN** saved responses, consumption state and outcomes are reused without duplicate paid submissions or assessments

#### Scenario: Stale cache or changed career evidence
- **WHEN** saved jobs are outside the current requested window or assessment inputs changed
- **THEN** stale jobs are excluded from fresh results and changed assessments are regenerated in new immutable state

### Requirement: Auditable partial report
Reports SHALL expose raw/unique/duplicate counts, freshness classes, relevance
outcomes, assessed/eligible counts, batch order, source/query stop reasons,
coverage limits and estimated versus actual retrieval cost. Reports SHALL state
that early stopping returns first qualifiers, not exhaustive best-five matches.

#### Scenario: Budget ends before five qualifiers
- **WHEN** acquisition stops at the allowance with fewer than five eligible jobs
- **THEN** the report returns the available qualifiers and explains incomplete coverage
- **AND** it does not imply zero suitable jobs exist in unsearched results
