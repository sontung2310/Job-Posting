# Job Search Automation

This project discovers recent jobs, scores each job description against verified
career-vault evidence, checks how well each current resume shows that evidence,
and prepares high-fit candidates for user approval.

For every discovery run, read and follow these files in order:

1. `config/search_targets.yaml`
2. `career-vault/AGENTS.md`
3. `docs/01-crawl.md`
4. `docs/02-categorize-score.md`
5. `docs/03-suggestions.md`
6. `config/obsidian_schema.md`
7. `config/notion_schema.md`
8. `docs/04-obsidian-write.md`
9. `docs/05-application-workspace.md`

Resume files:

- Place at least two text-extractable PDF resumes in `resumes/`.
- `scripts/run.sh` discovers all PDFs in that directory and checks each one.

Non-negotiable rules:

- Discovery runs cover only jobs posted in the previous 24 hours.
- Before paid job-source calls, run `python3 scripts/vault_evidence.py check`.
  Only verified, source-linked career-vault facts may earn scoring points.
- For Stage 2, use `./.venv/bin/python scripts/vault_evidence.py search` for
  every JD requirement. Pass its full original wording through `--requirement`
  and use `--term` only for literal terms from that JD. Hybrid scores retrieve
  candidates only; inspect the cited claim and source before scoring, and never
  let keyword or semantic similarity satisfy a hard requirement by itself.
- Use the Indeed plugin for Indeed, and the configured Apify MCP actors for
  LinkedIn and Seek. Do not substitute generic web search or browser scraping.
- Never apply for a job, contact an employer, or modify a resume.
- Never create or update an Obsidian package or Notion application page during
  the initial discovery run.
- After explicit approval only, write each approved, non-duplicate candidate to
  the destinations whose `WRITE_OBSIDIAN` and `WRITE_NOTION` flags are true.
  `WRITE_OBSIDIAN` and `WRITE_NOTION` default to false. A package may contain
  proposed résumé wording, but it must never change, replace, or imply creation
  of a résumé file. A cover letter is generated and saved only under the
  separate, explicit approval process in `docs/05-application-workspace.md`.
- Application packages and Notion pages are private operational records. Never
  use them as career-vault evidence and never place their contents in
  `logs/log.txt`.
- Present qualifying candidates and wait for explicit approval. `Approve all` or
  `Approve 1, 3` authorizes only the named candidates from the current report.
- Before any approved destination write, repeat the duplicate check across local
  active and archived records and, when Notion is enabled, the configured Notion
  application database.
- A run with zero new or qualifying jobs is a successful run. Report it plainly.
- Only when an explicit CLI batch runner supplies a private scoring-ledger run ID,
  record each scored JD with `./.venv/bin/python scripts/scoring_ledger.py record`.
  Use its canonical job URL only to produce the local hash, record the integer
  Candidate Evidence Fit, one of `qualified`, `below_threshold`, or `ineligible`,
  and a factual reason of at most 240 characters. Never put a full JD, evidence
  text, or raw URL in that ledger. Native Codex scheduled tasks do not expose the
  CLI token-usage event, so they must not create an incomplete or fabricated
  token-cost ledger; instead, include each scored JD's score and brief reason in
  the scheduled-task result.
- Append a short run summary to `logs/log.txt`; do not store full job descriptions
  or personal data in that public run summary. Detailed private score ledgers are
  Git-ignored under `logs/scoring/`.

Structured stage logs:

- Manual runs create `logs/DD-MM-YYYY/{discovery,scoring,suggestion,storage}.jsonl`.
  Existing `logs/scoring/YYYY-MM-DD.jsonl` files remain unchanged.
- Use `scripts/pipeline_log.py` for discovery, suggestion, and storage records.
  Discovery `fetch`, `reject`, and `retain` outcomes are mutually exclusive per
  platform/job; use stable job IDs or hashed `--job-url` values, never full JDs.
- Record one suggestion entry per qualifying job. The CLI finalizer enriches
  each suggestion with the completed-turn token, cost, and elapsed-time
  allocation after the Codex turn finishes. Never fabricate telemetry; if the
  finalizer cannot read the `turn.completed` usage event, the run must fail
  rather than be treated as a completed, measurable run.
- `WRITE_OBSIDIAN` and `WRITE_NOTION` are environment flags and default to
  false. A false flag is an intentional `skipped` destination, not a failure.
  Obsidian success requires the expected package path; Notion success requires
  confirming the job appears in the table.
