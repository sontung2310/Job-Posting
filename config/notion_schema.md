# Notion application database schema

## Destination

Notion is an optional second destination for approved application records. The
target database ID is supplied through `NOTION_DATABASE_ID`. The database must
be accessible to the connected Notion integration before `WRITE_NOTION=true`
is enabled.

The Notion page title should be:

```text
Company — Position
```

The canonical duplicate key is `Job URL`. Before creating a page, query the
target database for the canonical URL. If no URL match is available, use the
`Company` plus `Position` pair as a fallback duplicate check. Existing pages
must remain unchanged when a duplicate is found.

## Database properties

The live database is `DB Applications`. Keep the table display order below;
`resume_used` is intentionally second last and `cover_letter` is last.

| Property | Notion type | Value / format |
| --- | --- | --- |
| `Company` | Title | `Company — Position` |
| `Position` | Rich text | Job title |
| `Status` | Multi-select | `Found`, `Applied`, `Rejected`, `Interviewed`, `Accepted`, or `Offer` |
| `Date Found` | Date | Melbourne local discovery date |
| `Salary` | Rich text | Advertised salary, otherwise blank |
| `ATS Score` | Number | Integer from 0–100 |
| `Job URL` | URL | Canonical job URL |
| `Website` | URL | Explicit employer website, otherwise blank |
| `Source` | Select | `Indeed`, `LinkedIn`, or `Seek` |
| `Contact` | Email | Advertised contact email, otherwise blank |
| `strengths` | Rich text | Concise evidence-grounded strengths |
| `gaps` | Rich text | Concise honest gaps with their types |
| `suggested_cv_changes` | Rich text | Concise truthful proposed résumé changes |
| `resume_used` | Rich text | Selected immutable résumé filename |
| `cover_letter` | URL | Google Drive URL when a cover letter has been separately approved; blank otherwise |

Category and the former `Improvement Suggestions` property are intentionally
not part of the schema. Keep the detailed normalized JD, scoring evidence,
source-linked analysis, tailoring brief, and any operational fields not listed
above in the Notion page body or private local logs. Do not put raw vault
evidence or a cover-letter draft into database properties. The cover-letter
property and body section remain blank until the separate cover-letter approval
flow.

## Write and verification rules

- Only write when `WRITE_NOTION=true`; the default is false.
- Require `NOTION_DATABASE_ID` and an authenticated Notion connector before
  attempting a write. Missing configuration is a storage failure, not success.
- Write only explicitly approved, qualifying, non-duplicate candidates.
- Populate `strengths`, `gaps`, `suggested_cv_changes`, and `resume_used` from
  the approved scoring result. Leave `cover_letter` blank unless a separate
  cover-letter flow has been explicitly approved and produced a Google Drive
  URL.
- After creating a page, query the database again by `Job URL` and confirm
  that the job appears in the target table. Only then record Notion status as
  `confirmed` in `logs/DD-MM-YYYY/storage.jsonl`.
- Record `skipped` when `WRITE_NOTION=false`, and `failed` when an enabled write
  or post-write confirmation fails.
- Never overwrite an existing page or change a user's lifecycle status without
  a separate explicit instruction.
