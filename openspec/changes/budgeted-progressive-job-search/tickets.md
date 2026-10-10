# Local implementation graph

Integration branch: codex/budgeted-progressive-job-search.
Local OpenSpec tasks are the user-approved ticket tracker.

| Ticket | Scope | Dependencies | Status |
| --- | --- | --- | --- |
| R1 | Provider contracts, dates, bounded discovery acquisition and reuse; tasks 1.1, 2.1, 2.2 | none | resolved |
| C1 | Progressive session coordination, budgets, relevance, assessment/report integration; tasks 2.3, 3.1–3.3 | R1 interface contract; parallel implementation allowed | resolved |
| V1 | Saved-run replay and acceptance verification; tasks 1.2, 4.2 | R1, C1 | resolved |
| D1 | Skill/reference/routing updates; task 4.1 | R1, C1 | resolved |
| Q1 | Full verification and review fixes; task 4.3 | V1, D1 | resolved |

User-confirmed test boundaries: discovery CLI/bridge, assessment CLI,
progressive-session CLI/report. Final review baseline: a79c094. No paid live searches.
