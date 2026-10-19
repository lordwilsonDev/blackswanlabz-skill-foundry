# Security boundaries

Supported deployment: trusted local operator, one organization, loopback service. All authenticated readers share the organization's corpus. This is not a multi-tenant security boundary.

| Boundary | Enforcement | Limit |
|---|---|---|
| Identity | Random bearer tokens; only hashes stored in server config; fixed role map | Local files/admin are trusted; no SSO/MFA or token expiry |
| Retrieval | Exact operator grants, pinned Git commit / expected Dropbox revision; no redirect; response limits | Manual imports are operator assertions, not provider-authenticated provenance |
| Documents | Stored as text, citations are data, UI uses textContent | No general semantic prompt-injection detector; model proposals untrusted |
| Execution | Fixed trusted interpreter, no dynamic imports from payload, no eval/shell; macOS Seatbelt denies network/write | macOS profile allows file reads required for Python; do not use it for arbitrary untrusted code |
| Linux execution | No network, read-only root, unprivileged user, no capabilities, memory/CPU/PID caps | Docker runtime unavailable on build host; image build/scanning remains a gate |
| Review | Different authenticated principal; approval tied to immutable content hash; latest rejection blocks release | Does not prove different real-world people or subject-matter competence |
| Provenance | Content hashes, exact lines, source revision pins, active-source checks | Source content may still be false or misleading |
| Evidence | Reused MSB hash chain + durable SQLite outbox + reconciliation | Not externally notarized; trusted host admin can rewrite both chains |
| Browser | Bearer header only, no cookies/CORS, origin check, CSP, no-store, output escaping | Loopback HTTP; no remote deployment until a reviewed TLS/identity layer exists |

Roles: reader reads; builder reads/imports/assembles/runs/learns; reviewer reads/reviews/promotes/revokes; operator manages research and execution but cannot approve. Question-object authority never grants API privileges. No endpoint accepts identity or role from submitted data.

Unknown inputs, missing sources, changed revisions, expired questions, missing sandbox, unsupported connectors and failing checks are refused. API refusal receipts contain route and actor, not secrets or full prompts. Logs contain route and duration only. The SQLite database contains source text, questions and model output; protect the state directory and backups as confidential data. No private corpus is sent to a remote model; optional Ollama calls stay on loopback.

Revocation preserves historical evidence but removes sources from retrieval and makes dependent packages stale. Deletion/retention/export policies beyond this local system require organization-specific decisions. Do not treat a hash as a digital signature, structural verification as factual truth, or library RELEASED as production readiness.
