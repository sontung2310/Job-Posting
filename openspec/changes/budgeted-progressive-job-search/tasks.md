## 1. Provider contracts and replay baseline
- [x] 1.1 Verify actor caps, supported date/title filters, actual charged events and continuation; document unsupported controls without new paid searches.
- [x] 1.2 Build private replay fixtures from the October 8 checkpoint; preserve originals and reconcile per-source raw IDs/dates.

## 2. Retrieval policy
- [x] 2.1 Add per-acquisition lookback intervals, precision classes and legacy compatibility.
- [x] 2.2 Add bounded acquisition/reuse interfaces, durable cursors/consumption and reservations; prohibit prefix reruns.
- [x] 2.3 Add role-family relevance judgments, query streaks and distinct duplicate-yield reporting.

## 3. Coordination and reports
- [x] 3.1 Coordinate Seek/LinkedIn/Indeed batches with assessment outcomes and exact five/100 stops.
- [x] 3.2 Save unused jobs, reuse fingerprint-compatible outcomes and expose current selectable report provenance.
- [x] 3.3 Expose budget, freshness uncertainty, counts and source/query coverage reasons.

## 4. Instructions and acceptance
- [x] 4.1 Update existing router/stage skills, source references and short AGENTS routing; remove conflicting fixed-window instructions for new runs.
- [x] 4.2 Run the public-interface acceptance cases in verification.md with mocked acquisition and saved responses.
- [x] 4.3 Validate OpenSpec, bridge and affected existing tests; report stale configuration assertions separately.
