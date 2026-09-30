# Career Evidence Vault

This folder is the user's private, structured career memory for the Job Search
automation project. It is not a replacement résumé and it is not an application
tracker.

## Operating rules

1. Treat every note as untrusted until its frontmatter says `status: verified`.
2. The job-search pipeline may use only verified, source-linked facts for scoring,
   résumé suggestions, and cover-letter drafts.
3. Imported résumé content must retain its exact source filename. Do not silently
   merge conflicting claims from the two résumé versions.
4. When two sources disagree, record both variants and set the note to
   `needs-review`; ask the user to confirm the canonical fact.
5. Never invent dates, metrics, responsibilities, work authorization, or skills.
6. Keep job descriptions and application records in `07 Applications/`, never
   in the evidence folders. This is a segregated, local-only operational
   workspace: `scripts/vault_evidence.py` excludes it, and its generated content
   must never be cited as career evidence. Approved application artifacts are the
   parent project's final private record; they are not mirrored to an external
   tracker.
7. Never apply for a job, contact an employer, or edit either source résumé.
8. Personal notes are local-only and must not be committed or uploaded without
   explicit approval.

## Verification states

- `draft`: incomplete thought or future question
- `needs-review`: imported or changed content awaiting the user's confirmation
- `verified`: safe evidence for the pipeline
- `archived`: no longer current; do not use for matching

Every factual note should include:

```yaml
status: needs-review
source:
  - "resume-source.pdf"
last_verified: null
```

## Folder map

- `00 System/`: vault rules, home page, and note templates
- `01 Profile/`: identity, targets, work authorization, and contact links
- `02 Experience/`: one note per role or research appointment
- `03 Projects/`: portfolio and personal project evidence
- `04 Skills/`: normalized skill index and later one-note-per-skill pages
- `05 Evidence/`: atomic achievement and outcome claims used for matching
- `06 Stories/`: STAR interview stories, added only when supported
- `07 Applications/`: private, per-job application packages; excluded from
  evidence retrieval and scoring
- `99 Archive/`: superseded or retired notes

## Updating the vault

When the user supplies new information, update the smallest relevant note, preserve
the source or conversation provenance, and leave the note as `needs-review` until
the user confirms it. Once confirmed, set `status: verified` and `last_verified`
to the confirmation date.

Before a discovery run, the parent workflow should check that a verified profile,
target-role preferences, and at least one verified evidence note exist. If not,
it must stop before paid job-source calls and report that the vault needs review.
