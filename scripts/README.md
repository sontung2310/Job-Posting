# Scripts map

The four skills use these workflow entry points:

| Entry point | Responsibility |
| --- | --- |
| `.agents/skills/job-search/scripts/progressive.py` | Alternate bounded retrieval and scoring, reserve verified charges, reuse caches and freeze selection reports. |
| `run.sh` | Terminal launcher for retrieval, scoring or full pipeline; finalize real CLI usage. |
| `.agents/skills/job-retrieval/scripts/discovery_bridge.js` | Invoke Codex connector tools in supervised batches. |
| `.agents/skills/job-retrieval/scripts/discovery.py` | Plan searches, checkpoint responses, filter and deduplicate jobs. |
| `.agents/skills/job-scoring/scripts/assessment.py` | Cache shared inputs, inspect jobs, validate scores and publish the ranked report. |
| `.agents/skills/job-suggestions/scripts/approved_preparation.py` | Validate selection and save selected-only suggestions. |
| `readiness.py` | Cache local profile/PDF readiness; defer hybrid setup until eligible scoring. |

Internal modules are imported by those entry points:

| Module | Responsibility |
| --- | --- |
| `charge_contract.py` | Validate inspected actor/connector prices and enforceable total-charge arguments before paid acquisition. |
| `assessment_validation.py` | Job identities, fingerprints and condition validation. |
| `.agents/skills/job-scoring/scripts/scoring.py` | Validated Candidate Evidence Fit and Resume Coverage arithmetic. |
| `private_io.py` | Atomic private JSON writes. |
| `paid_operations.py` | Vault-scoped operation locks and durable uncertain-paid-work markers. |
| `condition_profile.py` | Verified profile-note loading. |
| `vault_evidence.py` | Eligible evidence parsing and local/hybrid retrieval. |
| `pipeline_log.py`, `scoring_ledger.py` | Operational records and explicit CLI usage accounting. |

Optional/manual utilities remain deliberately available: `index_vault_chroma.py`
refreshes hybrid vectors; `job_sources.py` verifies additional ATS/government
sources; `start-apify-mcp.sh` and `load-apify-token.sh` configure connector access.
The evidence and logging modules also retain useful standalone commands.

File names describe current responsibilities. Existing private checkpoint paths,
saved JSON, reports and historical records retain their original names and are
not migrated by this cleanup. Skills contain the actual workflow procedures.

Native scheduled tasks call the skills directly; they do not run this CLI launcher.
Full and scoring-only runs continue to the candidate report before selection.

Skill-local entry points are under `.agents/skills/<skill>/scripts/`: discovery
and its tool bridge belong to job-retrieval; assessment and score arithmetic
belong to job-scoring; approved_preparation.py belongs to job-suggestions.
The latter validates report selection and saves selected-only suggestions.
Shared modules listed above stay here; destination procedures are in docs/.
