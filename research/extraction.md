---
tags: [architecture, moie, skill-compiler, hermes, msb-v3]
status: proposed
phase: design (not built)
created: 2026-09-14
updated: 2026-09-14
---

# Skill Extraction Blueprint

**Author:** Wilson — lordwilsonDev
**Framework:** MoIE Axiom Inversion
**License:** MIT
**Version:** 1.0

## One-line thesis

> Inference is expensive. Validated capability is reusable.
> The model proposes, reality tests, the compiled procedure becomes infrastructure.

Repeatedly calling an LLM for the same bounded task is often wasteful. Instead: use the LLM to *discover* a procedure, independently *verify* it against reality/ground truth, then *compile* the validated behavior into a deterministic, versioned, governed runtime skill. The LLM is removed from the ordinary execution path but re-engaged whenever drift or an unknown case is detected.

## Lifecycle

```
Problem → LLM inference → Behavior observation → Pattern extraction
→ Candidate procedure → Independent verification → Safety/invariant verification
→ Compilation → Deterministic runtime → Telemetry → Drift detection → LLM re-engagement
```

## Key distinction

This does **not** claim to recover an LLM's internal reasoning (opaque, not reconstructible). It extracts *observable task behavior* across repeated runs — inputs, outputs, decision boundaries — not private cognition.

## The Six-Gate compile decision test

Before compiling any task, check:

1. **Repeatability** — does it recur (~5+ times → candidate; daily/hourly → priority)?
2. **Output boundedness** — can valid outputs be enumerated (APPROVE/REJECT/ESCALATE) vs. open-ended (creative writing)?
3. **Rule stability** — is the underlying world/business rule stable, periodic, or continuously changing?
4. **Observability** — can correctness actually be measured (ground truth, human review, downstream outcome)? If not, never silently promote.
5. **Cost of failure** — low/medium/high (financial, legal, safety, irreversible) — drives how much verification/human-gate is required.
6. **Detectability of failure** — will a wrong-but-successful execution (silent failure) be noticed? Silent failure requires independent monitoring, not just schema checks.

Decision matrix collapses to: not repeatable/not bounded → keep LLM or hybrid; repeatable+bounded+stable+observable+low-risk → compile; same but silent-failure-prone → compile + independent monitoring; unstable → hybrid.

## Extraction pipeline (condensed)

- **Phase 0 — Define the skill contract**: name, purpose, inputs, outputs, constraints, forbidden side effects, success criteria, risk class, owner, version.
- **Phase 1 — Observation**: run baseline + variation + adversarial + repeatability tests against the LLM; log every input/output/decision/external-outcome as structured data. Question isn't "did reasoning match" — it's "did task behavior stay stable."
- **Phase 2 — Extraction**: use an LLM *again*, but now to analyze the observation corpus (not to run the task) — identify decision boundaries, propose `IF/THEN` rules with provenance (source observations, confidence, counterexamples), and explicitly flag `OPAQUE` decisions rather than silently hard-coding unexplained patterns.
- **Coverage model**: every skill needs an explicit coverage spec (schema/domain/state/rule coverage). Default policy for anything outside it: `UNKNOWN → ESCALATE`, never `UNKNOWN → GUESS`.
- **Phase 3 — Verification** (independent from the Extractor where practical):
  - Test A: replay all historical observations, classify mismatches (RULE_GAP / LLM_VARIANCE / BAD_OBSERVATION / GROUND_TRUTH_CONFLICT / UNKNOWN).
  - Test B: compare against independent ground truth, not just LLM agreement (compiler can perfectly reproduce an LLM that's *consistently wrong* — behavioral equivalence ≠ correctness).
  - Test C: novel/unseen inputs (random, boundary, combinatorial, adversarial).
  - Test D: adversarial inputs — must handle, fail loudly, or escalate; never silently invent an answer.
  - Test E: independent safety invariants that sit *outside* the LLM-derived rule set and can block a rule's output (e.g., "never delete customer records" overrides any compiled rule that says otherwise).
  - Metrics are multi-dimensional (behavioral agreement, ground-truth accuracy, coverage, unknown-escalation rate, false-escalation, false-acceptance, safety violations, latency, cost) — no universal "95% match" threshold; thresholds depend on risk class.
- **Phase 4 — Compile**: candidate procedure → target runtime (Python/JS/YAML rules/n8n/shell/skill format), bundled with contract + tests + provenance + version + rollback info.
- **Phase 5 — Shadow mode**: compiled skill runs in parallel with the LLM before being authoritative. Every mismatch gets investigated and classified, not discarded.
- **Promotion**: gated on evaluated-case count + coverage + zero critical violations + accuracy/unknown-detection/performance thresholds — never just "ran for a week."

## Runtime loop (post-promotion)

```
Input → schema validation → coverage validation → skill execution
→ safety gate → action → verification → evidence → audit
```

Any boundary failure → `ESCALATE` (back to LLM).

## LLM re-engagement triggers

`UNKNOWN_INPUT`, `SCHEMA_CHANGE`, `RULE_MISS`, `DRIFT`, `POLICY_CHANGE`, `FORMAT_CHANGE`, `FAILED_VERIFICATION`, `LOW_CONFIDENCE`, `NEW_DOMAIN`, `HUMAN_REQUEST`. The LLM isn't removed permanently — it's removed from *unnecessary runtime execution*.

## Drift detection

Determinism guarantees repeatability of the procedure, not continued truth of its assumptions. Drift categories: input, schema, rule, policy, outcome, distribution. Detector monitors input/output distributions, unknown rate, escalation rate, error rate, downstream outcomes, human overrides. Threshold breach → **trigger review**, not automatic rewrite.

## Versioning & rollback

Every skill is versioned (rules, tests, observations, compiler version, source model+version, validation results, deployment timestamp, operator approval). Compiled artifacts are inspectable, diffable, testable, and revertible (`v3 → v2 → v1` on failure) — a structural advantage over keeping everything in LLM-land.

## Compiler architecture (4 components)

```
HARVESTER (generates/runs test inputs, records behavior dataset)
   → EXTRACTOR (LLM analyzes dataset → candidate skill spec, NOT authoritative)
   → VERIFIER (independent/deterministic — replay, novel/adversarial tests, invariants, metrics)
   → COMPILER (candidate + verification report → deployable artifact + contract + tests + provenance + version + rollback)
```

## Mapping onto existing stack

- **Hermes** = discovery/orchestration/compilation layer — observes repeated work, identifies extraction candidates, invokes LLM → verifier → compiler, registers + monitors skills, prefers the compiled skill at runtime when the contract covers the task. Extends [[Hermes-MSB-v3-Integration-Blueprint]].
- **MSB (v3)** = authorization/execution/verification/audit governance layer: `Intent → Skill Router → Skill Contract → ActionGate → Tool → Verification → Evidence → Audit`. See [[Hermes-MSB-v3-Integration-Blueprint]], [[MSB-v3-Neurosymbolic-Runtime-Blueprint]].
- **Local deterministic runtime** = the actual compiled skill execution.

Division of labor: Hermes discovers/compiles, Skill Compiler extracts/verifies/packages, MSB authorizes/executes/audits, local runtime does the deterministic work. Avoids every component trying to be its own autonomous reasoner.

## Authority hierarchy (must not be violated)

```
SAFETY / CONSTITUTION → SYSTEM POLICY → SKILL CONTRACT → VERIFIED RULES → EXECUTOR → LLM PROPOSAL
```

LLM proposals never outrank the safety boundary; a compiled skill can't redefine its own contract.

## Critical security rule

Never: `LLM generates rule → automatically authorizes privileged action`.
Always: `LLM candidate → verification → policy gate → authorization → execution`. High-risk capabilities keep mandatory human approval.

## Named failure modes to watch for

- **Overfitting** — reproduces observed examples, fails on novel input. Detect via novel-input testing.
- **Compiling an LLM mistake** — compiler perfectly reproduces a *consistently wrong* LLM. Detect via independent ground truth; don't compile without it.
- **Hidden assumption** — skill only works because of an unstated environmental condition. Detect via assumption extraction + perturbation testing.
- **World drift** — stays deterministic, becomes obsolete. Detect via outcome/distribution monitoring.
- **Coverage illusion** — treating "not seen before" as "impossible." Fix: explicit coverage boundaries + unknown-state handling.
- **Verification theater** — same LLM generates rules, tests, verification, *and* approval (correlated failure). Fix: separate generation from verification.
- **Architecture theater** — more agents ≠ more intelligence; can just correlate the same error ten times. Goal: minimum components, maximum *independent* evidence.

## What should NOT be compiled

Creative generation, open-ended research, novel strategy, rapidly changing domains, anything without measurable correctness, anything where human judgment is inherently part of the objective, anything with insufficient observations or an uncharacterizable decision boundary.

## Minimum viable first experiment

Don't build the whole compiler first. Pick one repeatable + bounded + low-risk + observable task (e.g., form response → category), run 20–50 observations, extract rules by hand, build a small deterministic implementation, compare vs. LLM + ground truth on accuracy/coverage/latency/cost/failure. Generalize the compiler only if that succeeds.

## Success criteria for a compiled skill

Explicit purpose/inputs/outputs/assumptions/coverage; deterministic execution; reproducible tests; independent verification; safety invariants; unknown-state handling; escalation path; provenance; version; rollback; runtime telemetry; drift detection. Only then does the LLM leave the ordinary execution path.

## Status

Design document only — zero build. Natural next step is the "library meetup" style minimum-viable experiment (one small repeatable task) before touching Hermes/MSB integration for real. Related: [[project_s_aos_guardian_loop]], [[project_msb_v3_audit_convergence]].
