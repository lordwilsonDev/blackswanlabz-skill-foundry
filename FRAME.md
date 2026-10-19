# BlackSwanLabz Skill Foundry: AI-native frame

This repository is a frame that another model can build upon. Its job is to turn a person's question and authorized knowledge into a reusable capability with a clear boundary and evidence of what happened. It does not require every future capability to be built into one factory first.

## The contract

`Question → authorized sources → method proposal → bounded skill → execution or teaching → verification → receipt → versioned reuse`

An AI model may propose interpretations, teaching material, or a new skill. A proposal does not grant itself permission, establish that a source is true, or approve its own release. The surrounding frame supplies identity, source scope, execution limits, independent review, and a durable record. More capable models can replace the proposal step without replacing those boundaries.

## How another model should build from it

1. Read the user's objective and inspect the existing skill library and repository sources. Reuse a capability when its contract covers the task.
2. Pin the source and identify the actual function the user needs. For Axiom Inversion Logic, separate the objective and function from the conventional process used to deliver it.
3. Produce a candidate skill with purpose, inputs, outputs, assumptions, coverage, failure conditions, permissions, source citations, and teaching or execution mode.
4. Test the candidate on ordinary, boundary, and adversarial cases. Keep source truth, model agreement, behavioral repeatability, and real-world outcome as separate questions.
5. Ask for independent review when the skill makes consequential claims or acts beyond its proven scope. Preserve the review result and evidence receipt with the skill version.
6. Reuse or revise the skill as sources and outcomes change. Unknown cases return to research or review; they do not silently expand the skill's authority.

## Interchangeable parts

| Part | Existing implementation | What another model can add |
|---|---|---|
| Intake | Question Engineering checker and authenticated operator | Better question formulation while preserving question identity and scope |
| Research | Pinned GitHub/Dropbox grants and source library | More authorized sources and stronger retrieval, with revision provenance |
| Method extraction | Cited structured passages; optional model proposals | Domain-specific extraction, AIL inversion, MoIE challenge, and held-out evaluation |
| Skill package | Versioned contract and `SKILL.md` export | Specialized procedures or teaching strategies under declared coverage |
| Execution | Restricted declarative worker | New reviewed capability adapters with their own permission and sandbox contracts |
| Verification | Structural checks, reviewer gate, MSB evidence spine | Independent domain tests, expert judgments, outcome checks, external anchors |
| Reuse | Capability Composer registry lookup | Better semantic matching without losing exact contract and version checks |

## Three uses of the same frame

- **Skill creation:** turn a repeatable method into a bounded procedure another model or person can apply.
- **Adaptive teaching:** use the same sources and skill contract to explain, practice, assess, and revise instruction for one learner. Self-reported progress is labeled as such.
- **Organizational second brain:** retrieve and apply current knowledge with citations, then record what was learned and which source revision supported it.

## What the current build proves

The local application demonstrates the interfaces and guardrails across all three modes. It compiles source-grounded workbooks, runs them in a sandbox, records receipts, and allows reviewed reuse. It has **not** established general method extraction, independent subject-matter truth, or production deployment. Those are tests for each new capability and environment, not prerequisites for understanding or extending this frame.

Start with [README.md](README.md) to run the local implementation, [docs/REUSE.md](docs/REUSE.md) to see the existing parts, and [reports/READINESS.md](reports/READINESS.md) for measured evidence and limits.
