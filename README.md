# BlackSwanLabz Skill Foundry

> **Status (2026-10-19): a working preview for one operator on one machine.** On a fresh copy of this repository all 162 tests pass, the local deployment checker passes, and the server starts on loopback only and refuses API calls without a token. It is not an enterprise deployment: multi-user identity, TLS, load targets, off-host backup, a Linux image and an independent security review are out of scope by design ([reports/READINESS.md](reports/READINESS.md) lists them). No independent reviewer has approved any generated skill, and the optional model features have not been exercised.
>
> **Origin:** built in a Codex (OpenAI) session on 2026-10-18 from existing BlackSwanLabz components (provenance in [research/provenance.json](research/provenance.json)), then re-tested independently with Claude on 2026-10-19. Free to use. Text under [CC BY 4.0](LICENSE), code under [MIT](LICENSE-CODE).

**Start with the [AI-native frame](FRAME.md).** It defines how other models can use existing research and components to create, test, teach, and reuse a capability. The runnable application below is one implementation of that frame; it is not the full extent of what future models can build from it.

A runnable, local, single-organization foundry built on Wilson's existing Capability Composer, Question Engineering harness, and MSB evidence spine. Research becomes a revision-pinned skill workbook with source citations, restricted execution, verification receipts, independent review, and a reusable library.

**Readiness: local validation only. Not production-ready.** The deterministic pipeline works without a model. It extracts structured passages; it does not claim to infer arbitrary methods reliably or to verify their truth. Optional local-model assistance produces explicitly unverified proposals. See [readiness evidence](reports/READINESS.md).

## Start

Python 3.12 or later. Runtime uses the standard library. macOS uses the existing Seatbelt sandbox. Linux requires Docker and a built worker image; execution refuses to fall back to an unrestricted host process.

```sh
python3 -m foundry --root runtime init --config runtime/operator.json
python3 -m foundry --root runtime seed
python3 -m foundry.server --root runtime --config runtime/operator.json --port 8787
```

Open http://127.0.0.1:8787. Initialization saves credentials in `runtime/operator.credentials.json`, mode 0600. Use the builder token to import, select evidence, assemble, run and learn. Assign the reviewer token to a different person for review/release. Two tokens controlled by one person do not establish independent review. Credentials are never committed or included in exports.

On this build machine initialization and seeding have already happened. Do not rerun `init` against the same configuration. Restart with the server command above.

## Workflow

1. Import an authorized text document, or retrieve an exact repository resource using an operator-configured source grant.
2. Search evidence and select documents. Source text remains data, even when it contains instructions.
3. Enter an objective and choose methodology, teaching, or second-brain mode.
4. Assemble a candidate with the inherited Question Engineering gate. Identical capability contracts reuse the existing package. Source changes invalidate dependent packages.
5. Run the fixed declarative workbook interpreter inside the OS sandbox. It has no network or write capability. No generated Python/shell is executed.
6. Inspect provenance, scope, safety and coverage checks, which are deterministic checks, not independent domain experts.
7. A separate authenticated reviewer records rationale. Release requires both approval bound to the package hash and a passing run receipt. Release means approved for this package's bounded coverage, not production certification.
8. Export a reusable `SKILL.md` and `package.json`, preserving citations, revisions, coverage and hash.

```sh
python3 -m foundry --root runtime export SKILL_ID /NEW/EXPORT/DIRECTORY
python3 -m foundry --root runtime integrity
python3 -m foundry --root runtime backup /NEW/BACKUP/DIRECTORY
python3 scripts/foundry_check.py --root runtime
python3 scripts/foundry_check.py --root runtime --production  # exits 2: gates remain unmet
```

## Modes

- **Methodology:** extracts headings and numbered/bulleted steps with exact line citations. AIL's Identify → Invert → Re-Derive → Compare → Synthesize and MoIE's roles come from the repository sources. Their research claims remain reported claims. Conflicting operator limits in research are not silently reconciled into authority.
- **Teaching:** persists per-learner practice, starts diagnostically, offers guided remediation after a low score, and advances after a self-reported score of at least 0.8. It labels self-assessment and grants no credential. `/api/lesson` accepts `skill_id`, optional `objective` and `score`. Optional model assistance can explain, give examples and exercises; those outputs require review.
- **Second brain:** retrieves only active source revisions, with excerpts and line citations. Revision changes/revocation invalidate dependent skills. There is no claim that keyword retrieval is comprehensive semantic understanding.

## Optional model assistance

Set `model` in the operator config to an already installed Ollama model. `/api/assist` accepts `query` and `mode` (`extract`, `teach`, `answer`, `invert`). The provider address is fixed to loopback, timeout/output limits apply, and no model tool calls execute. Source revisions are checked again after inference. Proposals and their prompt/source hashes are persisted. Model proposals do not automatically become verified skills or approvals. No model was installed on the build machine; live output quality remains unvalidated.

## Repository retrieval

`source_grants` in the config maps a grant ID to an exact resource:

```json
{"ail":{"kind":"github","repo":"lordwilsonDev/ail-moie-white-papers","commit":"03722d4dce78609d93ce313d7f210d21f2d86dd5","path":"papers/ail-operational-execution/README.md"}}
```

POST `/api/retrieve` with `{"grant_id":"ail"}` using a builder token. URLs, branches and traversal paths are rejected. Public GitHub reads need no token; private reads use `FOUNDRY_GITHUB_TOKEN`. Dropbox uses a separately supplied `FOUNDRY_DROPBOX_TOKEN`, exact file ID and expected revision. Desktop connector sessions are not copied into the application. The user selected repositories as the primary source for this build.

Connector contracts were checked against [GitHub contents documentation](https://docs.github.com/en/rest/repos/contents) and [Dropbox download documentation](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/download).

## Validation and operations

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

For Linux tests, build `deploy/Dockerfile.worker` and set `FOUNDRY_WORKER_IMAGE` to the image's immutable `sha256:` ID. Never mount the Docker socket into an exposed application container. The server remains loopback-only. Deployment templates, CI, monitoring examples, backup/restore and limitations are documented in [OPERATIONS](docs/OPERATIONS.md) and [SECURITY](docs/SECURITY.md).

The original composer and four existing domain skills remain available; see [upstream instructions](docs/CAPABILITY-COMPOSER.md). The Foundry uses its registry lookup but does not grant CRM/Slack write authority or reimplement those connectors.

Author of reused research and foundations: **Lord Wilson / BlackSwanLabz**. See [reuse inventory](docs/REUSE.md) and the hash-pinned [provenance manifest](research/provenance.json).
