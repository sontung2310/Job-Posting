# Design

## Instruction ownership

| Owner | Responsibility |
| --- | --- |
| AGENTS.md | Default full-pipeline routing, explicit alternate modes, configuration pointers, shared protections and approval boundary |
| job-retrieval | Discovery readiness, configured source queries, normalization, required-data/window/duplicate filtering, recovery, coverage and handoff |
| job-scoring | Scoring readiness, conditions, evidence retrieval, semantic judgments, score validation, qualifier suggestions, report and approved-preparation handoff |
| References | Connector facts, scoring definitions, destination write contracts and application-package contents |
| Helpers | Durable state, cached shared inputs, provenance checks, arithmetic, report identity and privacy-safe logging |

AGENTS.md names both skills with their exact repository paths and contains a
short ordered overview. It does not repeat phase commands or score formulas.
Both skills rely on shared protections rather than restating shared setup.
Sensitive actions retain their local enforcement checks. Career-vault rules
remain authoritative for eligible evidence and its verified sources.

Readiness is stage-specific: discovery checks only its prerequisites; scoring
checks verified profile, every current resume and selected retrieval mode.
Scoring-only does not initialize discovery credentials. The user need not invoke
a launcher to obtain the full workflow in chat.

## Routing and continuation

The pipeline starts only on an explicit job-search execution request or an
authorized scheduled task trigger. Ordinary conversation, questions about the
workflow, specification work and code reviews do not start discovery or scoring.

“Run the full job-search pipeline”, “get fresh jobs”, “find jobs from the latest
24 hours” and equivalent job-search execution requests route to discovery followed
by scoring. Explicit retrieval-only ends
at the handoff. Saved-job scoring resumes the selected handoff without discovery.
An explicit skill-only invocation retains that skill's scope. User lookback
precedence and the fixed original run window remain unchanged.

Persist progress and continue through all original jobs. Intermediate files,
small batch boundaries, token-heavy payloads and the existence of a checkpoint
are not completion criteria. Concrete failures preserve accepted work and are
reported with remaining jobs and a resume point. A source failure need not block
assessment of already retained jobs. Existing supervision and uncertain-paid
retry boundaries remain in force.

## Scheduled and CLI invocation

Keep scripts/run.sh as the terminal entry point for full, retrieval-only and
saved-job scoring runs. It remains a launcher, not another procedure owner.

Native scheduled Codex tasks execute the workflow directly in the local project
using AGENTS.md and the two skills. Their durable prompt explicitly requests the
full pipeline, its lookback and candidate-report stopping point. A native task
must not invoke run.sh to spawn another Codex process; that would duplicate the
agent runtime and make results and approval context harder to track.

A future morning schedule uses Australia/Melbourne time and the configured
lookback unless explicitly overridden. Scheduling is a separate explicit user
action: implementing this change creates no automation and assumes no morning
execution time. Both manual and scheduled entry points use the same stage
contracts, coverage, private state and reports. Scheduled execution has no
implicit candidate approval; each run ends with its report, or an honest empty
result or concrete blocker. Selected-candidate writes require later explicit
approval against that run's report. Document the local-project requirement that
the machine and desktop app be running and that connectors and files be available.

## Assessment and suggestions

Condition failure precedes requirement evidence retrieval. Passed or ambiguous
conditions proceed; ambiguity retains exact wording. Codex makes semantic
judgments; helpers validate and calculate Candidate Evidence Fit separately
from each resume's coverage. Qualification uses the configured exclusive
threshold: with the current value, 75 rejects and 76 qualifies.

Keep the existing public prepare/inspect/requirements/judgments seams where
practical. Read full shared profile/resume material once per unchanged run;
subsequent responses reference its identifiers. Compact progress uses coverage
counts/status and a private coverage handle instead of repeating every search.
Full original JDs and source excerpts remain inspectable in bounded pages.
Reducing boilerplate classification effort must preserve complete original-unit
accounting and compound requirement scope; it must not silently drop clauses.

Suggestion authoring follows the validated score decision. The helper can return
an actionable qualifier template through existing interactions before accepting
its final recommendations. Below-threshold jobs do not require suggestions.
For each qualifier, the canonical contract contains:

- jd_priorities: frozen requirement IDs, original scope and priority;
- strengths: concise verified claims with supporting citations;
- gaps: missing/partial support and unresolved conditions, linked to requirements;
- resume_plan: recommended source resume, relevant coverage gaps and prioritized
  supported changes, each explicitly marked review before adding.

Reuse validated facts and scores; suggestions cannot inflate scores or introduce
unsupported metrics. An absent category remains an explicit empty list rather
than an omitted field. Extensive tailoring stays after candidate approval.

## Candidate report and human selection

Save a private report and a machine-readable mapping with run/report identity,
immutable numbered entries, canonical job IDs/URLs and assessment provenance.
Sort qualifiers by descending fit with a deterministic tie-break. Present every
qualifier, the four suggestion sections, original manual-review wording, source
metadata and every resume's coverage. Show all outcome counts and discovery
coverage separately. State that no application records were written.

“Accept 1 and 2” resolves only against the current displayed report. Re-rendering
or resuming that report preserves its numbers. Unknown numbers, stale reports or
changed provenance do not authorize writes. Destination flags stay false by
default; candidate selection does not enable them. Enabled destinations repeat
duplicate/provenance checks and confirm writes independently. Disabled
destinations are reported as skipped. Cover letters retain separate approval.

## Reference migration

Rename docs/04-obsidian-write.md to docs/approved-destination-writes.md,
docs/05-application-workspace.md to docs/application-package-reference.md, and
docs/06-source-adapters.md to docs/additional-source-adapters.md.

The destination document owns approval-to-write operations and confirmation;
the package reference owns content/schema guidance and tailoring boundaries.
Shared prohibitions point back to their owner rather than restating a competing
procedure. Additional adapters load only for explicit use or maintenance, not
ordinary Seek/LinkedIn/Indeed discovery.

Update active links, evidence-source resolvers, allowlists and fingerprint paths
atomically. Inspect old repository-backed citations before migration; preserve
historical snapshots and accept their verified legacy references or migrate
current references with revalidation. Do not rewrite immutable historical
specifications/reports merely to satisfy a stale-link scan.

## Verification

Use existing launcher/assessment public seams and saved connector fixtures.
Routing/instruction checks verify actual task selection and completion wording;
a mocked CLI prompt alone cannot prove chat behavior. Perform an agent acceptance
run over a small saved handoff through the candidate report, without a new search
or paid cloud call. Exercise gate failure, ambiguity, below/equal/above threshold,
partial discovery, interruption/resume and numbered selection at destination
boundaries. Compare repeated response payload sizes and shared-input loads for
the same fixture; correctness and complete accounting are acceptance criteria,
not a promised production speedup.
