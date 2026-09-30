# Stage 1 — Discover and normalize jobs

## Preconditions

1. Read `config/search_targets.yaml`.
2. Run `python3 scripts/vault_evidence.py check`. If it fails, stop before paid
   Actor calls and report the missing vault prerequisite. Use only verified,
   source-linked vault facts in later scoring.
   Confirm hybrid retrieval is ready with `./scripts/run.sh --check`; this also
   verifies the local embedding runtime and model required by Stage 2.
3. Confirm both resume PDFs exist and contain extractable text. If either is missing
   or unreadable, stop before paid Actor calls because Resume Coverage cannot be
   calculated.
4. Confirm the Indeed and Apify tools are available. Confirm the local Obsidian
   application workspace exists; it is read-only during discovery.

## Source routing

For every title/location pair:

- Indeed: use the Indeed job-search tool and request jobs posted within 24 hours.
- LinkedIn: call Apify actor `curious_coder/linkedin-jobs-scraper`. Construct a
  LinkedIn public jobs search URL for the title and location with the LinkedIn
  `Last 24 hours` filter (`f_TPR=r86400`), and pass that search URL to the actor.
- Seek: call Apify actor `websift/seek-job-scraper` in form-input mode with
  `searchTerm`, `location`, `dateRange: 1`, `sortBy: "ListedDate"`, and the
  configured maximum results. The actor accepts `ListedDate` and
  `KeywordRelevance` for `sortBy`; use `ListedDate` for discovery so the newest
  listings are returned first.

Do not replace a failing source with generic web search. Continue with other sources
and report the failed source and error in the run summary.

## Date and result limits

- Accept only listings whose posting time is within the preceding 24 hours at run
  time. When a source offers only a calendar-day filter, apply that filter and then
  post-filter using the returned timestamp when available.
- Ignore jobs with no reliable posting date unless the source explicitly guarantees
  its query is limited to the last 24 hours.
- Stop at `max_results_per_search_per_source`. Report when a result set reaches the
  cap because the run may not be exhaustive.

## Normalize

Normalize every item to:

```json
{
  "source": "Indeed | LinkedIn | Seek",
  "source_job_id": "source identifier or null",
  "job_url": "canonical URL",
  "company": "company name",
  "position": "job title",
  "location": "normalized location",
  "posted_at": "ISO-8601 timestamp or date",
  "salary": "advertised salary text or null",
  "contact_email": "valid advertised email or null",
  "company_website": "explicit employer URL or null",
  "description_text": "plain-text full job description"
}
```

Strip tracking query parameters from job URLs while preserving parameters required
to identify the job.

## Deduplicate

1. Exact duplicate: same canonical job URL.
2. Cross-source duplicate fallback: normalized `company + position + location`.
3. Prefer the record with the fullest description; merge only non-conflicting fields.
4. Search local Obsidian application records in both `07 Applications/01 Active/`
   and `07 Applications/99 Archive/` for the canonical URL before scoring. Exclude
   jobs already saved. If URL search is inconclusive, check company and position.

Record counts for fetched, rejected-by-date, duplicate, and retained jobs per source.
