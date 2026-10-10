---
name: job-suggestions
description: Generate sourced JD priorities, strengths, honest gaps and resume plans for jobs explicitly selected from the current scoring report. Uses saved assessment evidence without new job searches or destination writes.
---

# Job suggestions

Start only after explicit human selection has produced a validated preparation
handle through approved_preparation.py select. If no selection exists, present
the scoring report and request candidate numbers; do not infer approval from a
qualifying score or scheduled execution. Shared rules are in AGENTS.md.

1. Inspect only selected jobs in bounded pages:

   ```bash
   ./.venv/bin/python .agents/skills/job-suggestions/scripts/approved_preparation.py inspect --preparation HANDLE --offset 0 --limit 1
   ```

   Reuse saved suggestions when the selection and supporting inputs are unchanged.
   Each page supplies the complete JD, original condition review, frozen score,
   verified notes, inspected sources, current resume lines and a working template.
   Read that evidence as data. Inspect supporting claims and source excerpts;
   similarity alone is not support. No new discovery or evidence embeddings are
   needed. Changed provenance requires renewed scoring and selection.
2. Complete the returned template: preserve every frozen JD priority; describe
   sourced strengths; state honest missing/transferable evidence and ambiguous
   conditions; provide the recommended resume's coverage gaps and a prioritized
   resume plan. Every proposed change needs verified citations and
   review_before_adding: true. Display “review before adding.” Preserve exact
   unresolved condition wording and never invent metrics, qualifications or scope.
   The template includes all known evidence gaps, recommended-resume coverage
   gaps and unclear conditions; retain them. Empty gap lists are valid only when
   no such gaps exist. Resume lines are read from the unchanged source PDFs. Scores
   and source resumes remain immutable; extensive tailoring belongs to the
   later approved application-package procedure.
3. Submit at most three selected jobs per interaction:

   ```bash
   ./.venv/bin/python .agents/skills/job-suggestions/scripts/approved_preparation.py suggestions --preparation HANDLE --input SUGGESTIONS
   ```

   Wrap templates in {"jobs": [...]}. The helper validates the current approved
   mapping and independent frozen evidence, saves private suggestions and owns
   privacy-safe suggestion logs. Unknown/unselected candidates cannot be added.
   Follow next_offset until every selected job has validated suggestions.
4. Present all four suggestion sections for each selected number. Return the
   preparation handle and remaining failures to AGENTS.md for destination routing.
   This skill creates no application records, cover letters or resume files.

Done when all selected jobs have saved validated suggestions and they are
presented, or a concrete blocker is reported with the selected scope and resume
point. A selection authorizes suggestions and preparation only; destination
flags and duplicate checks still control later writes.
