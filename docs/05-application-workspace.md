# Application workspace — private Obsidian packages and optional Notion mirror

## Decision

Store the canonical application package in Obsidian when `WRITE_OBSIDIAN=true`,
and optionally mirror it to the configured Notion application database when
`WRITE_NOTION=true`. Neither destination belongs in the evidence corpus. The
Obsidian package belongs in `career-vault/07 Applications/` so it can link
directly to verified career notes while `scripts/vault_evidence.py` excludes it
from validation, retrieval, and scoring. Its active and archive records are
Git-ignored to keep personal job descriptions and drafts local.

Use one self-contained Markdown note per approved job, rather than separate JD,
strength, résumé, and cover-letter notes. A single stable `job_id` and canonical
URL keep the material together, prevent link drift, and make the package useful
for later interview preparation.

| Information | Canonical home | May support scoring? |
| --- | --- | --- |
| Verified career claim | `01`–`06` Career Evidence Vault folders | Yes |
| Normalized JD, fit analysis, strengths, gaps, tailoring brief, and an approved cover-letter draft only | `07 Applications/01 Active/` | No |
| Original résumé PDFs | `resumes/` | Resume Coverage only |
| Application-tracker fields, normalized JD, and preparation details | Obsidian package and optional Notion application page | No |

## Creation gate and lifecycle

1. Stages 1–3 gather and report candidates but create no local package, Notion
   page, résumé file, cover letter file, external application, or contact.
2. `Approve all` or `Approve 1, 3` authorizes packages only for the named
   candidates in that report, after Stage 4 repeats the duplicate and eligibility
   checks.
3. For every approved, non-duplicate candidate, write only to destinations whose
   flags are true. Create the Obsidian package at
   `career-vault/07 Applications/01 Active/YYYY-MM-DD — Company — Position.md`
   from `00 System/Templates/Application Package.md`, and create the optional
   Notion page according to `config/notion_schema.md`.
4. Confirm each enabled destination independently. Preserve the Obsidian
   package as preparation history; when it is no longer active, move it manually
   to `99 Archive/`. Never delete or overwrite either destination automatically.

If a package already exists for the canonical URL or `job_id`, report it and
leave it unchanged unless the user explicitly asks to update that note. Approval
never authorizes an application submission or a source-résumé change.

## Required contents

The package must include the full normalized JD; Stage 2 match JSON, scores, and
requirement-to-evidence table; JD analysis; source-linked strengths; honest gaps;
the selected source résumé; and a tailoring brief. Use the template headings so
packages remain consistent. The cover-letter section remains empty unless the
user separately requests and later approves a letter.

Use Obsidian links for verified career notes. The only factual sources are the
selected résumé and linked `status: verified`, source-linked vault notes.
Generated text is always a draft. When a fact is supported by the vault but not
the selected résumé, label it `review before adding`; when a fact is unsupported,
do not phrase it as a claim.

## Resume and cover-letter boundary

The package is a tailoring brief, not a generated résumé. It may suggest a
summary, skills order, bullet revision, or manual filename, but it must not edit
or create a résumé PDF/DOCX. Proposed bullets retain only source-supported
metrics and scope.

Cover letters have a separate, explicit approval flow:

1. Creating or approving an application package does **not** authorize a cover
   letter. Stage 3 and Stage 4 must leave the cover-letter section empty.
2. Generate a letter only when the user explicitly requests it for an identified
   job, for example: `Generate a cover letter for Job X.` Use the job's approved
   package, selected résumé, and verified evidence; write the draft in that chat,
   not in Obsidian.
3. Ask the user whether they want revisions. Revise in the same chat as requested
   and do not save a version while the letter is still under review.
4. Save the final letter into that job's existing application package only after
   the user explicitly approves saving that specific cover letter, for example:
   `Approve this cover letter for Job X and save it.` A general job approval or
   a request to generate is not save approval.

The saved letter remains a reviewable draft, not a sent message. It may discuss
the role and company facts supplied by the JD, but must not invent company
research, a hiring manager, a referral, or a qualification. The user submits any
final materials manually.

## Operational safeguards

- Keep raw JDs, application drafts, and personal information out of Git and
  `logs/log.txt`.
- Never feed `07 Applications/` back to `vault_evidence.py` or use it to award
  Candidate Evidence Fit points.
- Keep the current two source résumés immutable. A manual tailored copy is
  outside this automation's write scope.
- Keep frontmatter `strengths`, `gaps`, and `suggested_cv_changes` concise; the
  application's Markdown body holds the detailed, source-linked version.
