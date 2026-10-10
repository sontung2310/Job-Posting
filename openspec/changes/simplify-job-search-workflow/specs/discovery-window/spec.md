# Configurable fixed discovery window

## ADDED Requirements

### Requirement: Resolve the effective lookback

Discovery SHALL resolve lookback hours from an explicit user run override,
otherwise configuration, otherwise 24. The selected value SHALL be a positive
integer; invalid selected values SHALL fail before source submission. One-off
overrides SHALL NOT modify persistent configuration. There SHALL be no
mandatory-24-hour validation or silent narrowing to 24 hours.

#### Scenario: No lookback supplied
- **WHEN** neither a run override nor configuration supplies a lookback
- **THEN** discovery uses 24 hours

#### Scenario: User requests 48 hours
- **WHEN** the user supplies 48 hours and configuration supplies 24
- **THEN** the run uses 48 hours without rewriting configuration

#### Scenario: Configured longer period
- **WHEN** configuration supplies 72 hours and there is no override
- **THEN** the run uses 72 hours

#### Scenario: Invalid selected value
- **WHEN** the selected value is zero, negative, fractional or nonnumeric
- **THEN** initialization fails explicitly before any paid source call
- **AND** no fallback duration is silently substituted

### Requirement: Persist an immutable run-start interval

Initialization SHALL save the effective lookback, original run-start time and
exact window endpoints. The accepted interval SHALL include reliable posting
timestamps from run start minus the chosen duration through run start. Resume
and retry SHALL use those endpoints unchanged. A conflicting resumed override
SHALL fail before source calls; changing the interval requires a new run.

#### Scenario: Delayed collection
- **WHEN** a 48-hour run resumes two hours after it started
- **THEN** filtering still uses the original 48-hour interval
- **AND** jobs posted after the original run start are excluded

#### Scenario: Resume with a different duration
- **WHEN** a saved 24-hour run is resumed with a conflicting 48-hour override
- **THEN** the conflict is reported without changing the checkpoint or submitting a new search

#### Scenario: Legacy checkpoint
- **WHEN** a legacy checkpoint has trustworthy original window endpoints
- **THEN** those endpoints are preserved without widening or moving them
- **AND** ambiguous legacy window metadata requires explicit recovery or a new run

### Requirement: Source filters must cover the requested interval

Configured source requests SHALL use a supported filter that covers the selected
window, with exact local filtering afterward. A broader supported filter MAY be
used for a source with coarse date options. A source unable to cover the period
SHALL expose a limitation and partial/failed coverage rather than silently use a
narrower period. Configured sources and result caps SHALL remain unchanged and
visible; a cap does not imply uncapped enumeration.

#### Scenario: Source offers a coarse broader period
- **WHEN** a source cannot filter exactly 48 hours but supports a broader covering period
- **THEN** the adapter uses that supported period and filters against the saved exact interval locally

#### Scenario: Source cannot cover the period
- **WHEN** no supported configured-source query can cover the requested window
- **THEN** the source limitation is reported explicitly
- **AND** narrower results cannot be presented as complete requested coverage

### Requirement: Reliable dates and honest coverage

Missing, calendar-only and relative posting labels SHALL be rejected unless
saved observation metadata and precision can prove their entire possible
posting interval lies within the saved window. A rolling provider date filter
alone SHALL NOT establish the fixed upper endpoint. Handoffs and reports SHALL
include the effective duration, original endpoints, source outcomes, caps and
limitations. Rejection reasons SHALL describe the selected window without
assuming it is always 24 hours.

#### Scenario: Unreliable date in a filtered source response
- **WHEN** a rolling date-filtered source returns a job without a reliable posting timestamp
- **THEN** the source filter alone cannot justify retaining it as inside the fixed window

#### Scenario: Exact endpoints
- **WHEN** reliable absolute posting timestamps equal either saved endpoint
- **THEN** they pass freshness validation
- **AND** timestamps outside either endpoint are rejected
