# Readiness record — 2026-10-18

> **Update 2026-10-19 (independent re-run, not part of the original record):** on a fresh unzip of the delivered archive, all 162 tests passed with none skipped; `scripts/foundry_check.py` exited 0 locally and 2 with `--production`, as designed; the server started on 127.0.0.1 only, served its page, and returned 403 for API calls without a token; the evidence-integrity check passed. For one operator on one machine these are the relevant gates. The verdict below is measured against enterprise acceptance gates and is left as written.

**Verdict: working local implementation; NOT PRODUCTION-READY.**

The requested Foundry has been implemented as an integrated local application, with a deliberately bounded execution contract. It does not yet fulfill the full ambition of a generally capable, independently validated AI instructor and autonomous skill compiler. Remaining implementation gaps are listed separately from unavailable external services below.

## Demonstrated

- **162 tests pass**: 128 preserved composer/connector tests and 34 new Foundry tests. `tests.txt` records the latest run. No skipped tests on this macOS run.
- Live GitHub retrieval succeeded for AIL and MoIE source documents pinned to commit `03722d4dce78609d93ce313d7f210d21f2d86dd5`; see `live-repository-retrieval.json`.
- All three modes assembled and ran through the real macOS sandbox with citations and receipts; see `end-to-end.json`. Generated exports remain CANDIDATE pending real independent review.
- Browser verification covered authenticated library loading, source selection, assembly, sandbox execution and teaching practice. The service is bound to loopback on port 8787. Browser screenshot capture timed out, so no screenshot-based visual approval is claimed. A pointer interception issue required DOM button activation for the final workflow check.
- macOS sandbox tests directly attempted a network connection and file write: both denied. Prompt-injection text was rendered as data and caused no external action.
- Negative tests cover role restrictions, self-review, stale/revoked sources, source/package/run/spine tampering, question identity/scope/expiry, revision drift, connector traversal/redirects, model proposals without authority, and lack of sandbox fallback.
- Concurrent duplicate assembly produced one package. Interrupted evidence delivery recovered through the outbox.
- Real local backup restoration verified its content and spine chain (`backup-restore.json`).
- Lint and Python compilation passed; JavaScript syntax check passed.
- Local deployment checker passed integrity and actual sandbox execution. Production checker exited **2** and reported `production_ready:false`.
- Thirty serial local executions recorded median ~37 ms and p95 ~44 ms in this environment (`latency.json`). This is a small workload measurement, not a throughput/SLO test.

## Reused foundations

Capability Composer base and four skills, its registry lookup, the existing Question Engineering checker, actual MSB evidence-spine storage/hash verification, AIL/MoIE research, and the prior skill-extraction blueprint. Source hashes, versions and modifications are recorded in `../research/provenance.json`.

## Remaining external dependencies / acceptance gates

- No Ollama model is installed. The optional live model provider has not produced or been evaluated on actual teaching/extraction outputs.
- No real independent reviewer has approved the generated capabilities. Test identities prove separation logic, not real-world expert independence.
- Docker is unavailable here; Linux image build, image scanning and CI have not been observed running.
- No remote deployment target, organization identity provider, external evidence notary, off-host backup or alert destination has been configured.
- MSB's running service was offline; reuse of its library is demonstrated, live service interoperability is not.

## Remaining implementation / validation scope

- Default extraction is bounded structured-line extraction, not a validated general methodology-inference engine. Optional model proposals remain separate, unverified artifacts. No automatic compilation of arbitrary generated code is supported.
- Teaching adaptation is persistent self-assessed practice plus optional model explanation; independent assessment, validated learning outcomes and credential issuance are not implemented.
- Second-brain retrieval is keyword-ranked and single-organization. Multi-tenant isolation, semantic retrieval evaluation and enterprise retention controls are not implemented.
- Deterministic checks verify provenance/contract integrity, not the truth of research claims or independent MoIE reasoning quality.
- Production identity/TLS, target-scale admission control, sustained load tests, SLO/alert verification, signed external receipt anchoring, disaster recovery and independent security review remain release gates.

## Bugs found and fixed during this build

1. Assessment timestamps defeated capability reuse, including under concurrent requests. Removed volatile assessment data from package identity, added concurrency regression tests.
2. Fresh intake IDs could create duplicate capabilities. Reuse now keys on the capability contract, not the intake ID.
3. A later negative review did not demote an already released package. Rejection now removes release status and blocks re-promotion.
4. Retrieval needed to check stored content hashes; corrupt source text now refuses retrieval.
5. Worker success needed comparison against the requested package; result verification now compares mode, exact workbook and side effects.
6. Mutations could proceed with a damaged evidence chain. Mutation authorization now checks integrity first.

No remote repository was pushed, no messages were sent, no public deployment was created, and no real candidate was self-approved.
