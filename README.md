# Job Search Automation

This repository finds recent jobs, filters them against configured titles and
locations, scores them against verified career evidence, and prepares an
approval report. It does not apply for jobs, contact employers, or modify a
resume.

There are two ways to use it:

- **Source verification:** fetch and validate the additional ATS and Australian
  government sources with scripts/job_sources.py.
- **Full pipeline:** run the Codex workflow across Indeed, LinkedIn, Seek, the
  additional sources, evidence scoring, resume coverage, and optional private
  Obsidian/Notion writes.

## 1. Prerequisites

For source verification:

- macOS or Linux
- Python 3.12
- Git
- Chromium, installed by Playwright during setup

For the full pipeline, also install:

- the Codex CLI
- pdftotext from Poppler
- the configured Indeed plugin
- Apify MCP access for LinkedIn and Seek
- an authenticated Notion connector if Notion writes are enabled

On macOS, install Poppler with Homebrew:

~~~
brew install poppler
~~~

## 2. Install the project

Clone the repository and create the project virtual environment:

~~~
git clone <repository-url>
cd <repository-directory>
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
~~~

Install the source runtime:

~~~
./.venv/bin/python -m pip install -r requirements-sources.txt
./.venv/bin/python -m playwright install chromium
~~~

The full pipeline also needs local semantic retrieval:

~~~
./.venv/bin/python -m pip install -r requirements-semantic.txt
~~~

Run the tests after installation:

~~~
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
~~~

## 3. Add your personal inputs

The full pipeline expects at least two text-extractable PDF resumes in:

~~~
resumes/*.pdf
~~~

scripts/run.sh discovers the PDF files automatically and checks each one.
Resume PDFs are Git-ignored; never commit them.

Replace or populate career-vault/ with your own verified evidence. Read
career-vault/AGENTS.md before editing it. Evidence must be source-linked and
verified before it can affect scoring.

Resume PDFs must contain selectable text. Check them with:

~~~
for resume in resumes/*.pdf; do
  pdftotext "$resume" - | head
done
~~~

## 4. Configure job searches

Edit config/search_targets.yaml. A search is a title/location pair:

~~~yaml
timezone: "Australia/Melbourne"
lookback_hours: 24

searches:
  - title: "AI Engineer"
    location: "Melbourne"
  - title: "Machine Learning Engineer"
    location: "Sydney"
~~~

Production discovery only accepts jobs posted in the previous 24 hours. The
source verifier uses --days 7 by default so that a new adapter can be tested
against a larger recent window.

For additional sources, a job matches only when:

1. the source provides a reliable posting date within the requested window;
2. every meaningful word in the configured title occurs in the job title; and
3. the configured location appears in the source location.

A zero-match result is valid. The pipeline does not broaden searches just to
manufacture results.

## 5. Configure additional sources

Edit config/source_boards.yaml. Keep this file limited to public endpoints;
do not put credentials in it.

| Source | Configuration |
| --- | --- |
| Greenhouse | Add each employer's public board API URL under boards. |
| Ashby | Add the employer's public posting API URL under boards. |
| Lever | Add the employer's public postings API URL under boards. |
| Workday | Add the employer's verified public tenant/CXS jobs URL and API URL. |
| SmartRecruiters | Add the employer's public company_id. |
| APS Jobs | Uses the configured APS search page and Playwright. |
| State portals | Add or update portal URLs under state_portals. |

The current Australian state adapters are Victoria, New South Wales, Western
Australia, and South Australia. Some government portals use bot protection or
change their frontend without notice. The adapter fails closed when it cannot
verify a result page; it must not emit guessed jobs.

## 6. Configure credentials and connectors

Create a Git-ignored .env file for the full pipeline:

~~~dotenv
APIFY_TOKEN=your_apify_token
NOTION_DATABASE_ID=your_notion_database_id
~~~

Restrict its permissions:

~~~
chmod 600 .env
~~~

APIFY_TOKEN is required by scripts/run.sh for the LinkedIn and Seek Actors.
NOTION_DATABASE_ID is required only when Notion writes are enabled.

The local .codex/config.toml points to the Apify launcher using an absolute
path. This machine-specific file is not part of the reusable source commit.
On another computer, create or update it so the command points to that
computer's absolute path for scripts/start-apify-mcp.sh, then restart Codex.

The full pipeline also requires:

- Indeed plugin authentication;
- the configured Apify MCP server and Actors;
- the local ResumeSkills listed in docs/03-suggestions.md; and
- a Notion connector with access to the configured database when enabled.

Use the Indeed plugin for Indeed and the configured Apify Actors for LinkedIn
and Seek. Do not replace those integrations with generic web search.

## 7. Verify the additional sources

Run every enabled additional source over the seven-day verification window:

~~~
./.venv/bin/python scripts/job_sources.py --days 7
~~~

Run selected sources while developing an adapter:

~~~
./.venv/bin/python scripts/job_sources.py \
  --sources greenhouse aps_jobs state_portals \
  --days 7
~~~

The command prints JSON containing fetched, recent, and
keyword_location_matches counts for each source. A successful source with no
current matching job reports zero matches. An inaccessible or unparseable
source reports an error instead of returning unverifiable data.

The source layer is implemented in scripts/job_sources.py and documented in
docs/06-source-adapters.md. It uses direct HTTP for public structured feeds
and bounded Playwright workers for rendered portals. Playwright source runs
require network access and an installed Chromium browser.

## 8. Run the full preflight

Before a full discovery run, check the local evidence, resumes, semantic model,
cost configuration, and required files:

~~~
./scripts/run.sh --check
~~~

The first semantic search downloads the local MiniLM model. Allow that download
once if needed:

~~~
./.venv/bin/python scripts/vault_evidence.py search \
  --requirement "Build and operate retrieval-augmented generation systems" \
  --term "RAG" \
  --allow-model-download
~~~

The model and embedding index stay local under models/ and are Git-ignored.

## 9. Run daily discovery

After preflight passes:

~~~
./scripts/run.sh
~~~

The workflow creates an approval report under reports/ and privacy-safe
stage logs under logs/DD-MM-YYYY/. It waits for explicit approval before any
application record is written.

The normal approval replies are:

~~~text
Approve all
~~~

or:

~~~text
Approve 1, 3
~~~

Approval applies only to the named candidates in the current report. It does
not authorize applications, employer contact, or resume changes.

## 10. Enable optional private writes

Writes are disabled by default. After reviewing the workflow and schemas, set
only the destinations you want:

~~~
WRITE_OBSIDIAN=true ./scripts/run.sh
WRITE_NOTION=true ./scripts/run.sh
~~~

Before enabling them, read:

- config/obsidian_schema.md
- config/notion_schema.md
- docs/04-obsidian-write.md
- docs/05-application-workspace.md

Obsidian and Notion application records are operational records, not career
evidence. The workflow repeats duplicate checks before writing and records a
disabled destination as skipped, not as a failure.

## 11. Add or maintain a source

For an existing adapter:

1. Add or update its public endpoint in config/source_boards.yaml.
2. Run the source alone with --sources <source_id> --days 7.
3. Check that recent jobs have reliable dates, canonical URLs, titles, and
   locations.
4. Confirm returned jobs match config/search_targets.yaml.
5. Add parser fixtures and unit tests in tests/test_job_sources.py.
6. Update docs/06-source-adapters.md if the source has special behavior.
7. Run the full test suite and a live smoke test.

For a genuinely new provider, add an Adapter implementation, register it in
the ADAPTERS map, normalize records into the shared Job dataclass, and fail
closed when the source cannot prove posting date or job identity. Avoid adding
credentials, broad scraping fallbacks, or speculative abstractions.

## 12. Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing .env | Create .env with APIFY_TOKEN for the full pipeline. Source-only verification does not need it. |
| pdftotext is required | Install Poppler and confirm pdftotext is on PATH. |
| Semantic retrieval is not ready | Install requirements-semantic.txt, then run the one-time model-download command above. |
| Playwright browser error | Run ./.venv/bin/python -m playwright install chromium. |
| Zero matching jobs | Check title spelling, city names, posting dates, and the source's current inventory. Zero is a valid result. |
| HTTP 403 or Cloudflare | The portal is blocking automated access. Do not bypass it blindly; record the limitation or add an official structured feed. |
| Notion write fails | Confirm NOTION_DATABASE_ID, connector authentication, database sharing, and config/notion_schema.md. |

## 13. Project map

- AGENTS.md — non-negotiable workflow and safety rules.
- config/search_targets.yaml — title/location searches and discovery policy.
- config/source_boards.yaml — additional source registry.
- scripts/job_sources.py — source retrieval, normalization, freshness, and matching.
- scripts/run.sh — full preflight, discovery orchestration, and approval report.
- career-vault/ — verified personal career evidence.
- docs/01-crawl.md through docs/06-source-adapters.md — detailed workflow rules.
- tests/ — deterministic parser, logging, ledger, and evidence tests.

When changing behavior, update the relevant configuration, tests, and docs
together. Keep the production 24-hour policy separate from the seven-day source
verification window.
