# Application package reference

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

## Creation and lifecycle

Load this reference only after current-report selection. The operational approval,
duplicate checks, destination flags and confirmation procedure are owned by
[approved destination writes](approved-destination-writes.md). This document owns
package contents and detailed tailoring.

Preserve packages as preparation history. The user may manually move inactive
records to `99 Archive/`; an existing record remains unchanged unless the user
explicitly requests an update.

## Required contents

Use the frozen scoring report and the selected jobs’ validated job-suggestions output. The package must include the full normalized JD; assessment match JSON, scores, and
requirement-to-evidence table; JD analysis; source-linked strengths; honest gaps;
the selected source résumé; and a tailoring brief. Use the template headings so
packages remain consistent. The cover-letter section remains empty unless the
user separately requests and later approves a letter.

Use Obsidian links for verified career notes. The only factual sources are the
selected résumé and linked `status: verified`, source-linked vault notes.
Generated text is always a draft. When a fact is supported by the vault but not
the selected résumé, label it `review before adding`; when a fact is unsupported,
do not phrase it as a claim.

## Detailed tailoring after candidate approval

Load the relevant installed resume skills for the approved preparation branch:
`job-description-analyzer`, `resume-ats-optimizer`, `tech-resume-optimizer`,
`resume-tailor` and `resume-bullet-writer`. Use their analysis to prepare a sourced
summary candidate, truthful skills order and at most three supported bullet
revisions. Preserve the validated scores; keyword/formatting advice is not a new
score. State an unavailable skill honestly and keep every addition grounded in
selected-resume lines or verified source-linked claims. These skills never
authorize source-resume edits or invented metrics. `cover-letter-generator` is
reserved for the separately requested letter process below.

## Resume and cover-letter boundary

The package is a tailoring brief, not a generated résumé. It may suggest a
summary, skills order, bullet revision, or manual filename, but it must not edit
or create a résumé PDF/DOCX. Proposed bullets retain only source-supported
metrics and scope.

Cover letters have a separate, explicit approval flow:

1. Creating or approving an application package does **not** authorize a cover
   letter. the candidate report and approved preparation must leave the cover-letter section empty.
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

