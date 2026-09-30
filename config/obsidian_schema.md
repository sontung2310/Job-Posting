# Obsidian application-record schema

## Canonical location

Each approved, non-duplicate job is one private Markdown record at:

```text
career-vault/07 Applications/01 Active/YYYY-MM-DD — Company — Position.md
```

The YAML frontmatter below is the schema for an Obsidian Base or table. The
record's Markdown body holds the normalized JD, full evidence table, and detailed
application preparation material. `07 Applications/` is excluded from evidence
retrieval and scoring.

## Frontmatter properties

Keep this order so an Obsidian table can show `Resume Used` immediately before
the final, user-owned `Cover Letter` column.

| Order | Obsidian property | Value / format |
| ---: | --- | --- |
| 1 | `type` | Always `application` |
| 2 | `status` | `approved`, then user-managed lifecycle status such as `applied`, `rejected`, `withdrawn`, or `archived` |
| 3 | `job_id` | Stable `YYYY-MM-DD--company--role` identifier |
| 4 | `company` | Employer name |
| 5 | `position` | Job title |
| 6 | `location` | Normalized job location |
| 7 | `source` | `Indeed`, `LinkedIn`, or `Seek` |
| 8 | `job_url` | Canonical job URL |
| 9 | `posted_date` | ISO-8601 posting date when available |
| 10 | `date_found` | Date the job entered the current discovery report, in `Australia/Melbourne` |
| 11 | `approved_date` | Date of explicit user approval, in `Australia/Melbourne` |
| 12 | `salary` | Advertised salary text, otherwise blank |
| 13 | `contact` | Advertised contact email, otherwise blank |
| 14 | `website` | Explicit employer website, otherwise blank |
| 15 | `candidate_evidence_fit` | Integer 0–100 from Stage 2 |
| 16 | `resume_coverage` | Map containing both résumé coverage scores |
| 17 | `last_updated` | ISO-8601 date of the latest approved record change |
| 18 | `strengths` | Short list of evidence-grounded strengths from Stage 3 |
| 19 | `gaps` | Short list of honest Stage 3 gaps, including their type |
| 20 | `suggested_cv_changes` | Short list of truthful proposed résumé changes |
| 21 | `resume_used` | Selected immutable source résumé filename |
| 22 | `cover_letter` | **Leave blank.** User may later enter a local `.docx` path or Google Drive URL after separately approving that letter. |

There is intentionally no `category` property. Stage 2's required `category`
value remains in the fit JSON in the Markdown body; it is not an Obsidian tracker
column.

## Write rules

- Create a record only after explicit approval of a qualifying, non-duplicate
  candidate. Never overwrite an existing record without a new explicit instruction.
- Search both `01 Active/` and `99 Archive/` by canonical `job_url`, then by
  normalized company, position, and location before creating a record.
- Keep `strengths`, `gaps`, and `suggested_cv_changes` concise in frontmatter;
  preserve the complete source-linked analysis under the corresponding body
  headings.
- Do not guess blank optional values. Do not put the full JD, raw evidence table,
  or generated cover-letter text into frontmatter.
- Leave `cover_letter` blank during approval and Stage 4. A general job approval
  does not authorize a letter draft or save.
