# Archaeology and reuse decisions

Inspected 2026-10-18, through the connected GitHub/Dropbox tools and local repository files.

| Component | Evidence | Integration decision |
|---|---|---|
| Capability Composer | Existing code, registry, four skills and adversarial tests | Base repository preserved; reuse registry lookup rather than recreate connectors |
| Question Engineering | `qe-irf-harness/harness/qe.py` and `status.py`, commit 8f54e051c90069533ad74164e945c4dcbf6e64d0 | Vendored existing parser/assessment, explicit wall-clock check; Foundry adds authenticated authority and selected-source scope checks |
| MSB evidence spine | GitHub clone at 62453af3a0481e3bdba8073790a272f2e21a1fc3 | Reused actual DecisionEvidenceStore; removed MSB settings dependency in favor of required explicit DB path; preserved MIT notice |
| AIL | `ail-moie-white-papers`, pinned 03722d4dce78609d93ce313d7f210d21f2d86dd5 | Repository research is cited source material; five-stage method preserved |
| MoIE | Same repository, inversion-challenge paper | Role definitions preserved as research; structural experts labeled deterministic, not model experts |
| GST | Inspected governance store, expert recomputation, MSB adapter and stated limitations | Did not transplant its logical-clock/agent authority model into real HTTP identity; used its separation of proposal, acceptance and consumption as an architectural reference |
| Skill extraction blueprint | Local vault document, status explicitly proposed | Coverage/unknown handling, source observation, independent verification, version/rollback guide implementation; no claims of recovered private reasoning |
| Existing installed skills | AIL-CSM 20-stage harness, question engineering, governed execution, intent/reality fidelity | Inventory/architecture inputs; not automatically executed as trusted code |

The initial `~/msb-v3` and `~/deepseek-harness` paths were runtime/log remnants, not source checkouts. MSB :8766 was unreachable. The source was then inspected from GitHub; live MSB service integration is not demonstrated. Ollama responds but reports zero installed models.

Connected Dropbox: keyword searches for Axiom Inversion, Skill Foundry, inversion and BlackSwanLabz returned no results. Root listing completed: six media files, three folders. Each folder listing completed empty. No research documents were imported from Dropbox. The user then directed this build to use repositories.

No existing repository was overwritten. Work is in an isolated clone, branch `codex/skill-foundry`. No remote push, public release or deployment occurred. Local source copies without a declared license remain user-owned/private deployment material; do not assume public redistribution permission for every vendored file.
