# Job search runtime

## ADDED Requirements

### Requirement: Optional embeddings, no generation API

The project SHALL use Codex for reasoning without direct generation API calls.
Keyword-only mode SHALL work without OpenAI/Chroma packages or credentials and
SHALL make no embedding/index/probe/cloud calls. Hybrid mode SHALL permit only
text-embedding-3-small model API operations and Chroma vector operations. Existing
verified-evidence and application exclusion rules SHALL be retained.

#### Scenario: Keyword-only deployment
- **WHEN** hybrid is false and cloud packages/keys are absent
- **THEN** local retrieval and Codex assessment can proceed

#### Scenario: Generation endpoint invoked
- **WHEN** project code attempts Responses or chat generation
- **THEN** acceptance fails even if the generated judgment is correct

### Requirement: Simple readiness, recovery and honest logs

Vault/profile/resume readiness SHALL be checked before paid discovery. Unchanged
hybrid index inputs SHALL be reused. Private state and existing logs SHALL retain
completed work without duplicate records; changed inputs SHALL invalidate stale
assessments. Real wall time, coverage and available usage SHALL be reported.
Unavailable token/cost telemetry SHALL remain null/unavailable, not fabricated.
Existing required CLI turn finalization SHALL retain its separate full-turn scope.
No new state engine or telemetry subsystem is required.

#### Scenario: Unchanged evidence index
- **WHEN** eligible fingerprint/model/schema/count match
- **THEN** no document re-embedding/upsert is performed

#### Scenario: Native token usage unavailable
- **WHEN** the host exposes no completed-turn usage
- **THEN** operational results may complete with explicitly unavailable Codex telemetry

### Requirement: Local checks before one live retrieval test

Development SHALL use saved responses, synthetic fixtures and saved JDs to check
arguments, parsing, dates, pagination, duplicates, recovery and assessment before
live retrieval. A necessary live test SHALL start only when those checks pass and
the source path is ready. It SHALL select exactly one platform and one title/location,
for example AI Engineer in Melbourne, with at most three results where supported.
An Apify test SHALL submit at most one Actor run. Other platforms SHALL NOT start
automatically. Saved results SHALL be reused for subsequent checks.

Retrieval and scoring skills SHALL be tested independently using this saved-data
handoff. A scoring-only test SHALL make no job-source calls; the split SHALL NOT
increase the live-test allowance.

#### Scenario: Ready LinkedIn acceptance test
- **WHEN** local checks pass and LinkedIn is the selected test platform
- **THEN** one AI Engineer/Melbourne search may run with at most three results
- **AND** Seek and Indeed are not searched as part of that test

#### Scenario: Live test fails
- **WHEN** the live test reveals an error
- **THEN** it is diagnosed and fixed locally using the saved response
- **AND** another live search requires explicit user authorization, not an automatic retry loop

#### Scenario: Actor still running
- **WHEN** the single submitted Actor has a confirmed run ID
- **THEN** polling and dataset reads may continue on that run without a new submission

### Requirement: Performance evidence without extra paid benchmarks

A single-source test SHALL be described only as validation of that tested path.
Saved-JD runs MAY measure assessment quality/time. Full 10–15 minute performance
SHALL be measured from an authorized normal production run with complete coverage,
including preflight and reporting. Implementation acceptance SHALL NOT require
repeated paid crawls or full-source benchmarks without further authorization.

#### Scenario: Single search is fast
- **WHEN** the one live search completes quickly
- **THEN** it does not establish performance for the full configured workflow

#### Scenario: Normal full run overruns
- **WHEN** a full authorized run takes longer than 15 minutes
- **THEN** real coverage/time and the bottleneck are reported without dropping required work
