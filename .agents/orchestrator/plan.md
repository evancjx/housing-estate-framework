# plan.md — SG-Estate-Framework Enhancement Project Plan

## Architecture & Codebase Overview
- The project is a Singapore Estate Liveability Framework scoring pipeline.
- It splits into Provision (objective, comparable) and Liveability/Value (demand-side, relative).
- Models are located in `models/`, scrapers in `scrapers/`, data in `data/`, and tests in `tests/`.

## Milestones

| # | Milestone Name | Scope | Dependencies | Status |
|---|----------------|-------|--------------|--------|
| 1 | Exploration & Baselining | Run baseline tests, inspect codebase, analyze all requirements R1-R4, locate target files. | None | PLANNED |
| 2 | R1: Pipeline Integration | Wire the 5 unwired ingesters into the pipeline and provision/value models. | M1 | PLANNED |
| 3 | R2: Private Scrapers & Value | Implement and run scrapers for Districts 15 & 16, merge URA private data, update value model. | M1 | PLANNED |
| 4 | R3 & R4: UI & Test Suite | Regenerate UI deliverables (comparison table & framework diagram), expand test suite for new components. | M2, M3 | PLANNED |
| 5 | Victory Audit | Final verification run of the entire pipeline, all tests, and run Forensic Audit. | M4 | PLANNED |

## Coordination Folder Structure
Agent metadata will be stored in:
- `.agents/orchestrator/` — Orchestrator coordination
- `.agents/explorer_baselining/` — Milestone 1 exploration subagent
- `.agents/worker_r1/`, `.agents/reviewer_r1/` — Milestone 2 implementation & review
- `.agents/worker_r2/`, `.agents/reviewer_r2/` — Milestone 3 implementation & review
- `.agents/worker_ui_tests/`, `.agents/reviewer_ui_tests/` — Milestone 4 implementation & review
- `.agents/auditor_victory/` — Milestone 5 Forensic Auditor
