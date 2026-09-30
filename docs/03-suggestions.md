# Stage 3 — Generate truthful application suggestions

Generate an application strategy only for jobs with `ATS_score > 75` and no unmet
hard requirement. Stage 2 remains the sole source of Candidate Evidence Fit and
Resume Coverage; this stage must not recalculate or relabel either as an employer
ATS score.

## Skills used in Stage 3

The current Codex session must expose the following installed ResumeSkills. Apply
them in this order, while following the project rules below:

1. `job-description-analyzer` — structure the JD into required, preferred,
   responsibility, soft-skill, and domain requirements; identify employer
   priorities and any JD red flags.
2. `resume-ats-optimizer` — compare exact JD terms against the selected résumé,
   including their placement and truthful alternatives. It is a keyword and
   formatting review, not a replacement score.
3. `tech-resume-optimizer` — for AI Agent, Computer Vision, or Hybrid jobs,
   assess technical depth, relevant projects, and ATS-safe technical-skill
   ordering.
4. `resume-tailor` — produce a targeted, evidence-grounded change plan without
   editing a source résumé.
5. `resume-bullet-writer` — improve only selected, supported bullets. Its
   examples never authorize invented metrics, scope, tools, dates, or outcomes.

If a required skill is not available in the session, state that fact and do not
pretend it was used. Restart Codex if necessary so the installed skills are
discovered. Do not substitute generic advice silently.

## Cover-letter explicit gate

Do **not** invoke `cover-letter-generator` in this stage. It is reserved for a
later, explicit user request to generate a cover letter for an identified job.
Neither a qualifying score, job approval, Obsidian record creation, nor application-package
creation authorizes a cover-letter draft or save.

## Truth and provenance rules

Every positive claim, proposed résumé phrase, and cover-letter statement must be
traceable to one of:

- the selected résumé, labelled `selected résumé`; or
- a `status: verified`, source-linked Career Evidence Vault note, linked as
  `[[path/to/note]]` and labelled `review before adding` when absent from the
  selected résumé.

Never turn a semantic similarity, keyword hit, skill name, or ResumeSkills
example into proof. Never manufacture a number merely because the bullet-writing
skill recommends quantification. Do not assert an ATS formatting defect unless it
was actually observed while inspecting the résumé file. A draft cover letter may
refer to the job and company as stated in the JD, but must not claim company news,
products, culture, a hiring-manager name, a referral, or research that was not
provided by the JD or another cited source.

## Required analysis

Produce the following for each qualifying candidate. Keep the approval report
concise; preserve the complete, source-linked material for the approved local
application package described in `docs/05-application-workspace.md`.

1. **JD analysis** — list the highest-priority required and preferred
   requirements, exact terms to surface, and two or three employer priorities.
   Mark employer priorities as `inference` and tie each to a JD phrase or
   responsibility.
2. **Strengths to lead with** — identify two to four differentiated, direct or
   transferable matches. For each, name the JD requirement, the supporting
   selected-résumé text or verified vault note, and why it is relevant. Do not
   claim the candidate is better than other applicants.
3. **Gaps and honest response** — classify every meaningful gap as exactly one
   of the following:
   - `resume visibility` — supported by verified vault evidence but omitted or
     buried in the selected résumé; mark it `review before adding`.
   - `phrasing` — already true in the selected résumé but needs the JD's accurate
     terminology surfaced naturally.
   - `transferable` — supported by related evidence but not the exact requirement;
     state the limitation honestly.
   - `unsupported` — no selected-résumé or verified-vault evidence; do not add it
     to a résumé or cover letter. Label a practical next step as `learn before
     applying` or `demonstrate with a small project` when useful.
4. **Résumé improvement plan** — recommend, in priority order:
   - a two- to three-sentence summary candidate;
   - a truthful skills-section ordering and exact keywords to surface;
   - experience/project bullets to move higher; and
   - at most three proposed bullet revisions, each with its source and a
     `review before adding` label when it adds vault-only wording.

   A proposed bullet can strengthen an action, context, or result only when all
   of those details are supported. Otherwise ask a focused verification question
   instead of completing the bullet. Keep standard ATS headings and a simple,
   text-first layout; do not recommend keyword stuffing.
## Approval report

Return a numbered list sorted by descending ATS score. Each candidate must show:

- company, position, location, source, posting date, and canonical URL;
- the three-key match JSON from Stage 2, the two Resume Coverage scores, and the
  selected résumé's coverage gaps;
- advertised salary/contact when present;
- a compact JD-analysis, strengths, gaps, and résumé-improvement summary; and
- any unmet hard requirement.

The approved Obsidian application's frontmatter stores separate concise
`strengths`, `gaps`, and `suggested_cv_changes` lists. The full job description
and tailoring brief belong in that application's Markdown body. Do not generate,
draft, or save a cover letter during Stage 3.

## CLI telemetry

The suggestion command records the job identity while the Codex turn is still
running. Token usage, estimated cost, and elapsed time are not available at
that point. After the turn completes, `scripts/scoring_ledger.py finalize`
reads the `turn.completed` usage event and enriches every suggestion record for
the run using the same equal-share batch estimate used by the private scoring
ledger. The record must show `usage_available: true`, `usage_source:
turn.completed`, and an `allocation_method` explaining that the values are
allocated across scored JDs.

If the completed-turn usage event is missing, finalization fails. Do not replace
the missing values with zeros or guessed estimates.

End with: `No Obsidian application records have been written. Reply "Approve all" or "Approve 1, 3" to prepare only the named candidates.`

If there are no qualifying new jobs, state that this is a normal successful result
and do not ask for approval.
