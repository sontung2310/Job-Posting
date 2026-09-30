# Structured source adapters

`scripts/job_sources.py` is the deterministic source layer for the additional
providers. It follows the provider-module pattern used by the referenced
career-ops project: each source has a parser, all parsers emit the same Job
shape, and filtering happens before scoring.

The production discovery policy in `config/search_targets.yaml` remains a
24-hour window. The adapter command defaults to a seven-day window because it
is also the source verification tool requested for this branch:

```bash
./.venv/bin/python scripts/job_sources.py --days 7
```

The command reads title/location pairs from `config/search_targets.yaml` and
only emits jobs when:

1. the source supplied a reliable posting date within the requested window;
2. all meaningful words in a configured title occur in the job title; and
3. the configured city occurs in the source location.

The JSON summary reports fetched, recent, and keyword/location-matching counts
for every enabled source. A zero matching-job count is valid when the source
has no current role for the configured searches; jobs are never widened to
nearby keywords merely to manufacture a result.

## Configuration

Source endpoints and ATS employer boards live in
`config/source_boards.yaml`. Public ATS endpoints do not require credentials.
Workday is tenant-specific, so each employer needs its verified public CXS URL.
APS Jobs and the non-Victoria state portals use bounded Playwright workers. APS,
South Australia, and the public WA Government Jobs search host expose rendered
records or JobPosting JSON-LD with posting dates. The NSW portal currently
returns an HTTP 403/Cloudflare security page in this environment, so the NSW
worker fails closed instead of emitting unverifiable jobs. The Victoria adapter
remains lightweight HTTP because its listing and detail pages are server-rendered.

Do not use the seven-day verification command as a replacement for the normal
24-hour discovery policy, and do not treat `updated_at`, closing dates, or the
retrieval time as a posting date.
