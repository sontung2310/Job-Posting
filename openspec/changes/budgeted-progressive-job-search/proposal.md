# Budgeted progressive job search

## Why

The October 8 run downloaded 692 Apify entries, including 278 repeated entries
within sources, broad keyword matches and Seek results from a two-day request.
The user wants fresh, relevant jobs with useful stopping decisions and reuse,
rather than exhaustive retrieval before scoring.

## What Changes

- Apply the selected lookback directly at provider submission, default 24 hours.
- Alternate a bounded Seek batch, LinkedIn batch and Indeed batch, assessing each
  batch before another acquisition; stop at five eligible jobs or 100 assessments.
- Stop low-relevance queries dynamically, without a fixed result-position cutoff.
- Reuse saved compatible responses, queued jobs and completed assessments.
- Reserve a configurable default USD 0.50 retrieval allowance before paid calls.
- Distinguish exact freshness from provider-filtered, uncertain posting times.
- Require verified scraping continuation capability; dataset pagination alone
  does not count as incremental acquisition or cost saving.

## Impact

The job-search router coordinates retrieval and scoring through existing stage
interfaces. Retrieval owns acquisition, relevance, freshness, duplicates and
coverage; scoring owns gates, evidence and fit. No new skill is required.
The fixed-run-window policy in simplify-job-search-workflow and source reference
is superseded for new runs by submission-relative intervals. Legacy checkpoints
retain their original policy. Historical results and personal source files stay
immutable. Selection, suggestions and destination approval boundaries stay intact.

## Non-goals

No paid acceptance crawl, actor substitution, schedule creation, application
submission, scoring formula redesign or promise of exhaustive/best-five coverage.
