# Stage 4 — Write approved jobs to configured destinations

This stage is prohibited during the initial discovery run. Run it only after the
user explicitly approves numbered candidates from the current report.

## Destination flags

The environment controls each destination independently:

```bash
WRITE_OBSIDIAN=true
WRITE_NOTION=true
```

Both flags default to `false` when unset. A false flag means that destination is
intentionally skipped; it is not a write failure. Never enable a destination
implicitly because a candidate was approved.

For Notion writes, `NOTION_DATABASE_ID` must identify the target application
database and the Notion connector must be authenticated. Read
`config/notion_schema.md` before enabling `WRITE_NOTION`.

## Approval boundary

- `Approve all` authorizes every candidate in the current report.
- `Approve 1, 3` authorizes only those candidate numbers.
- Approval never carries forward to another run.
- Do not interpret general encouragement or scheduling the task as write
  approval.
- An approval authorizes preparation records only. It never authorizes an
  application submission, employer contact, résumé modification, or cover-letter
  creation.

## Before writing

1. Re-read `config/obsidian_schema.md`, `config/notion_schema.md`, and the
   package template at
   `career-vault/07 Applications/00 System/Templates/Application Package.md`.
2. Resolve `WRITE_OBSIDIAN` and `WRITE_NOTION`. For every false flag, do not
   call or mutate that destination and record it as `skipped`.
3. For Obsidian, repeat the duplicate check against both
   `career-vault/07 Applications/01 Active/` and
   `career-vault/07 Applications/99 Archive/`: first by canonical `job_url`, then
   by normalized company, position, and location when needed.
4. For Notion when enabled, query the configured database by canonical `Job URL`
   before creating anything. If no URL match is available, use `Company` plus
   `Position` as the fallback duplicate check. An existing page is a duplicate
   and must remain unchanged.
5. Reconfirm `ATS_score > 75`, no hard requirement is unmet, and the candidate
   was explicitly approved.

## Shared record content

Both destinations use the same approved candidate payload. Preserve only facts
from the current report, selected résumé, and source-linked verified evidence:

- company, position, location, source, canonical URL, and posting date;
- salary, contact, and website only when actually advertised;
- Candidate Evidence Fit and both Resume Coverage scores;
- source-linked strengths, honest gaps, and suggested résumé changes;
- the selected immutable résumé filename; and
- the normalized full JD and detailed preparation material in the record body.

Never populate absent values with guesses. Keep application records out of the
Career Evidence Vault retrieval corpus and never put full JDs or personal data in
`logs/log.txt`.

## Obsidian write behavior

When `WRITE_OBSIDIAN=true`, create one local application record per approved,
non-duplicate candidate at:

```text
career-vault/07 Applications/01 Active/YYYY-MM-DD — Company — Position.md
```

Create it from the application-package template and populate its frontmatter
according to `config/obsidian_schema.md`:

- set `status: approved` and `approved_date` to the current date in
  `Australia/Melbourne`;
- retain the normalized source, canonical URL, salary, contact, and website only
  when actually provided;
- write separate concise `strengths`, `gaps`, and `suggested_cv_changes` lists;
- set `resume_used` to the selected immutable source résumé; and
- leave `cover_letter: ""` blank.

Obsidian is successful only when the expected Markdown path exists after the
write. If the flag is false, do not create the file and record status `skipped`.

Populate the Markdown body with:

1. source and canonical link;
2. normalized full job description;
3. the three-key Stage 2 match JSON, where `ATS_score` is Candidate Evidence Fit;
4. the Candidate Evidence Fit scoring evidence table;
5. both Resume Coverage scores and the selected résumé's gaps;
6. the source-linked JD analysis, strengths, gaps, and expanded CV-change brief;
7. missing or unmet hard requirements; and
8. an empty Cover Letter section for the user.

## Notion write behavior

When `WRITE_NOTION=true`, create one page in the database identified by
`NOTION_DATABASE_ID`, following `config/notion_schema.md`:

- use `Company — Position` as the page title;
- map the shared approved candidate payload to the defined database properties;
- write separate `strengths`, `gaps`, and `suggested_cv_changes` values;
- set `resume_used` to the selected immutable résumé filename;
- place the normalized JD, scoring evidence, source-linked analysis, and
  tailoring brief in the page body;
- leave the URL property `cover_letter` blank; and
- do not overwrite an existing page or alter its user-managed lifecycle status.

After creating the page, query the target database again by `Job URL`. Notion
is successful only when the job is confirmed to appear in the table. Record
status `confirmed` after that check. Record `failed` when the connector,
database ID, write, or confirmation is unavailable. If the flag is false,
record status `skipped` without calling Notion.

## Storage logging and final report

For each approved candidate, write one privacy-safe storage record:

```bash
./.venv/bin/python scripts/pipeline_log.py storage-job \
  --run-id "$PIPELINE_RUN_ID" \
  --job-url "<canonical-url>" \
  --approved true \
  --write-obsidian "$WRITE_OBSIDIAN" \
  --obsidian-status "written|skipped|failed" \
  --write-notion "$WRITE_NOTION" \
  --notion-status "confirmed|skipped|failed"
```

After all approved candidates are processed, run:

```bash
./.venv/bin/python scripts/pipeline_log.py storage-summary \
  --run-id "$PIPELINE_RUN_ID"
```

The summary reports total approvals, per-destination requested/written/skipped/
failed counts, and whether all requested destination writes succeeded.

Finally report records created, duplicates skipped, intentionally disabled
destinations, and failures with their local paths or Notion page references.
State clearly that no résumé was modified and no application was submitted.
