# Stage 2 — Categorize and calculate job fit

`ATS Score` is this project's transparent **Candidate Evidence Fit** estimate. It
measures how well a job description is supported by verified, source-linked facts
in the Career Evidence Vault. It is not an employer's private applicant-tracking
score.

## Evidence retrieval

Before scoring, run:

```bash
python3 scripts/vault_evidence.py check
```

For every JD requirement, retain the original requirement wording and retrieve a
hybrid shortlist from the vault. Supply the full wording with `--requirement`;
add `--term` only for exact tools, acronyms, or phrases present in the JD. The
full requirement drives semantic retrieval; supplied terms drive the token-based
keyword signal. For
example:

```bash
python3 scripts/vault_evidence.py search \
  --requirement "Build and operate retrieval-augmented generation experiences that return grounded answers" \
  --term "RAG" \
  --term "LangChain"
```

The tool combines literal keyword matches with local embedding similarity over
eligible Obsidian sections. It returns the component scores and retrieval paths
for each candidate. The MiniLM model is stored under `models/` and receives
only local text; the vault is never uploaded. The downloaded model lives under
`models/sentence-transformers/`; the persistent section vectors and requirement
query cache live under `models/vault-embeddings/`. On a new machine, install
`requirements-semantic.txt` and make the first model download explicit with
`--allow-model-download`.

The command returns only verified, source-linked evidence candidates. It is a
shortlist, not proof: read the returned claim and source before awarding points.
The scoring agent may use JD context to choose exact `--term` values at runtime,
but must not maintain or rely on a fixed synonym map. Never award a point for an
unverified note, a vague mention, a keyword hit, or semantic similarity alone.

When several requirements are ready at the same time, they may be sent as one
batch to avoid repeated tokenizer and framework dispatch overhead. The input is
a local JSON array; each object uses the same `requirement`, `terms`, `limit`,
and `compact` fields as `search`:

```bash
./.venv/bin/python scripts/vault_evidence.py batch-search \
  --input .state/requirements.json
```

The persistent evidence service deduplicates identical requests, batches unique
requirement embeddings, and caches complete result payloads. It refreshes the
index automatically when the eligible vault changes.

## Candidate Evidence Fit (100 points)

Start with these category budgets:

| Component | Points | What it measures |
| --- | ---: | --- |
| Explicit must-have skills | 35 | Required languages, frameworks, platforms, and methods |
| Responsibilities and demonstrated experience | 25 | Comparable work and outcomes |
| Domain/tool alignment | 15 | Relevant AI, product, cloud, data, CV, or LLM work |
| Seniority and scope | 10 | Years, ownership, leadership, production responsibility |
| Education/certification | 5 | Requirements stated or clearly preferred in the JD |
| Contextual keyword coverage | 10 | Correct terminology used in truthful context |
| **Total** | **100** | |

For each category that appears in the JD, split its budget between its
requirements. Use priority `3` for mandatory or repeated requirements, `2` for a
stated standard requirement, and `1` for a preferred or supporting requirement.
Within a category, divide points proportionally by priority. If a whole category
is absent, redistribute its budget proportionally across the categories that are
present so the total available score remains 100.

Example budget allocation before evidence is assessed:

| Category | Requirement allocation | Total |
| --- | ---: | ---: |
| Must-have skills | RAG 15, Python 10, Azure 10 | 35 |
| Responsibilities | Build RAG 15, evaluate quality 10 | 25 |
| Domain/tool alignment | LLM product work 15 | 15 |
| Seniority/scope | 3+ years 10 | 10 |
| Education | Relevant degree 5 | 5 |
| Contextual keywords | API, Docker, monitoring 10 | 10 |
| **Total** |  | **100** |

Score every requirement from verified evidence:

- **Direct** — the evidence explicitly demonstrates the requirement: earn 100%.
- **Transferable** — the evidence clearly demonstrates a closely related
  capability, but not the exact requirement: earn 50%.
- **Missing** — evidence is absent, vague, or unverified: earn 0%.

Round the final Candidate Evidence Fit total to the nearest integer. Keep an
internal evidence table with the JD requirement, allocated points, evidence path
and heading, source, strength, earned points, and gap.

## Hard requirements

Treat an explicitly `must`, `required`, or `mandatory` skill, licence,
qualification, work-authorisation condition, or application eligibility condition
as a hard requirement. If verified vault evidence cannot support it, label the
job **ineligible**. Do not generate suggestions or include an ineligible job in
the approval report, even if its raw Candidate Evidence Fit exceeds 75.

Preferred requirements reduce the score when missing but do not make a job
ineligible.

## Resume Coverage and category

Extract text from both PDFs and assess each against the same JD requirements and
point allocation. This produces two separate **Resume Coverage** scores. Select
the resume with the higher coverage; if tied, select the one covering more
high-weight hard requirements.

Resume Coverage is a readiness signal, not an eligibility gate. A verified vault
fact that is absent from the selected resume earns Candidate Evidence Fit points
but must be reported as evidence to review before surfacing in an application.

- `AI Agent`: the JD primarily requests LLMs, agents, RAG, evaluation, AI product
  engineering, backend/frontend integration, or full-stack AI delivery.
- `Computer Vision`: the JD primarily requests image/video understanding,
  detection, segmentation, tracking, OCR, 3D vision, camera systems, or CV model
  deployment.
- `Hybrid`: the JD explicitly contains at least two substantive AI Agent signals
  and at least two substantive Computer Vision signals.

The candidate-facing JSON contains exactly these three keys:

```json
{
  "category": "AI Agent | Computer Vision | Hybrid",
  "recommended_resume": "primary-resume.pdf | secondary-resume.pdf",
  "ATS_score": 0
}
```

`ATS_score` is Candidate Evidence Fit. Report the two Resume Coverage scores and
the scoring evidence table outside this JSON.

Only jobs with `ATS_score > 75` and no unmet hard requirement qualify for the
approval report. A score of exactly 75 does not qualify.

## CLI batch scoring ledger

This ledger applies only to a manual CLI batch that supplies a scoring-ledger run
ID. Immediately after finalising every JD that was scored, write one private
draft record using that supplied run ID:

```bash
./.venv/bin/python scripts/scoring_ledger.py record \
  --run-id "<run-id>" \
  --job-url "<canonical-job-url>" \
  --company "<company>" \
  --position "<position>" \
  --score "<rounded Candidate Evidence Fit>" \
  --status "<qualified|below_threshold|ineligible>" \
  --reason "<factual explanation, at most 240 characters>"
```

Record every JD that reached Stage 2, including low-scoring and ineligible JDs.
The command hashes the URL and never writes the raw URL. The reason must be a
short outcome explanation, not a JD, evidence table, source text, or personal
data.

When the single CLI run completes, the runner reads its JSON usage event, records
the batch's elapsed time and token-cost estimate, then divides each total equally
by the number of scored JDs. The private JSONL log is stored under
`logs/scoring/` and is Git-ignored. Each per-JD value is deliberately labelled
an **equal-share batch estimate**; it is not a measurement of the tokens or time
used for that individual JD. A zero-JD batch still records its batch summary and
is successful, but has no per-JD allocation. Local embedding retrieval has no
separate API token charge.

Native Codex scheduled tasks do not expose a CLI JSON usage event to their agent.
They therefore must not write an invented token or cost value. Instead, their
scheduled-task result must include each Stage 2 score and a brief factual reason.

## Acceptance examples

| Situation | Expected result |
| --- | --- |
| Candidate Evidence Fit is 75 | Do not qualify because the threshold is strictly greater than 75. |
| Candidate Evidence Fit is 88, but a mandatory licence has no verified evidence | Mark ineligible and keep it out of the approval report. |
| A 10-point requirement has clearly transferable evidence | Award 5 points and label it transferable. |
| Both resumes have the same Resume Coverage | Select the one that covers more high-weight hard requirements. |
| The vault proves Azure deployment but the selected resume does not mention it | Award Candidate Evidence Fit points, lower Resume Coverage accordingly, and label it `review before adding`. |
