# Generate suggestions after human selection

## Why

The user wants job-scoring to end at its ranked report and detailed suggestions
only for jobs they select. Earlier two-skill and pre-selection-suggestion decisions
are superseded by this explicit workflow correction.

## What Changes

- Scoring publishes qualifying results without waiting for suggestions.
- AGENTS.md routes selected report numbers to a new job-suggestions skill.
- A separate approved_preparation helper validates selections and stores only
  selected-job suggestions without altering report scores.
- Destination preparation stays in its existing shared documents, after suggestions.
- Stage-specific scripts and source/scoring references live inside their skills;
  shared helpers and destination documents remain at repository level.

## Impact

Active skill paths, CLI paths, report contracts, selection/suggestion persistence,
launcher stop point, documentation and fixture tests change. Historical private
state and reports are preserved. This does not create a schedule or run discovery.
