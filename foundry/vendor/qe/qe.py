"""Question Engineering: turn a consequential question into a governed object,
decide whether it may be consumed, and prove the harness notices when the
question's meaning is changed underneath it.

Differences from the v1.0 prototype this replaces (each was reproduced against
the prototype before being fixed; see tests/test_qe.py):

  * mutations are APPLIED and run through the real assess() + Registry, not
    only listed;
  * temporal validity and authority status are evaluated, not just present;
  * a universal-absence proposition over a partial scope fails;
  * PASS is reachable (instrument status is computed by calibrate(), not
    hard-coded);
  * no constant-vs-constant "distinction" checks that cannot fail.
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .status import now_utc, parse_ts, stable_hash

VERSION = "1.1"

QUESTION_ID_RE = re.compile(r"^Q-[A-Za-z0-9._-]+$")
VALID_STATUSES = {"PROPOSED", "TESTABLE", "BLOCKED", "RESOLVED", "SUPERSEDED", "INVALIDATED", "UNKNOWN"}
NON_CONSUMABLE_STATUSES = {"BLOCKED", "SUPERSEDED", "INVALIDATED"}
VALID_SPEECH_ACTS = {
    "QUESTION", "ASSERTION", "OBSERVATION", "REPORT", "HYPOTHESIS",
    "RECOMMENDATION", "AUTHORIZATION", "DECISION", "WARNING", "REFUSAL",
}
VALID_EVIDENCE_CLASSES = {
    "OBSERVED", "DERIVED", "INFERRED", "REPORTED", "EXTERNAL",
    "REPRODUCED", "UNVERIFIED", "CONTESTED", "MODEL_PROPOSAL",
}
# Only these classes, with a source, may satisfy a required-evidence item.
ACCEPTABLE_EVIDENCE = {"OBSERVED", "REPRODUCED", "DERIVED", "EXTERNAL"}
CONSUMABLE_AUTHORITY = {"VALID", "ACTIVE"}

REQUIRED_FIELDS = [
    "question_id", "version", "speech_act", "referent", "proposition", "scope",
    "universe", "authority", "temporal_validity", "consumer", "purpose", "status",
]
# Changing any of these changes WHAT is being asked, so the question needs a
# new version (or id). status / assumptions / evidence_required do not.
IDENTITY_FIELDS = (
    "speech_act", "referent", "proposition", "scope", "universe",
    "authority", "temporal_validity", "consumer",
)

# Heuristic: propositions phrased as absence/negative-existence claims.
ABSENCE_RE = re.compile(
    r"\b(no|none|never|absent|missing|nonexistent|not found|not present|"
    r"does not exist|doesn't exist|do not exist|there is no|there are no)\b",
    re.IGNORECASE,
)


class QEInputError(ValueError):
    """The input could not be parsed into a Question at all."""


class RegistryError(RuntimeError):
    """The registry file exists but cannot be trusted; never overwrite it."""


@dataclass
class Check:
    check_id: str
    status: str  # PASS | FAIL | BLOCKED | INFO
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Question:
    question_id: str
    version: int
    speech_act: str
    referent: str
    proposition: str
    scope: str
    universe: list[str]
    authority: dict[str, Any]
    temporal_validity: dict[str, Any]
    consumer: dict[str, Any]
    purpose: str
    status: str = "PROPOSED"
    obligations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)
    expected_state_change: str | None = None
    failure_condition: list[str] = field(default_factory=list)
    parent_question_id: str | None = None

    @classmethod
    def from_dict(cls, payload: Any) -> "Question":
        if not isinstance(payload, dict):
            raise QEInputError("question must be a JSON object")
        missing = [k for k in REQUIRED_FIELDS if k not in payload]
        if missing:
            raise QEInputError("missing required fields: " + ", ".join(missing))
        try:
            version = int(payload["version"])
        except (TypeError, ValueError) as exc:
            raise QEInputError("version must be an integer") from exc
        for name in ("authority", "temporal_validity", "consumer"):
            if not isinstance(payload[name], dict):
                raise QEInputError(f"{name} must be an object")
        if not isinstance(payload["universe"], list):
            raise QEInputError("universe must be a list")

        def strs(key: str) -> list[str]:
            value = payload.get(key, [])
            if not isinstance(value, list):
                raise QEInputError(f"{key} must be a list")
            return [str(x) for x in value]

        return cls(
            question_id=str(payload["question_id"]),
            version=version,
            speech_act=str(payload["speech_act"]),
            referent=str(payload["referent"]),
            proposition=str(payload["proposition"]),
            scope=str(payload["scope"]),
            universe=[str(x) for x in payload["universe"]],
            authority=dict(payload["authority"]),
            temporal_validity=dict(payload["temporal_validity"]),
            consumer=dict(payload["consumer"]),
            purpose=str(payload["purpose"]),
            status=str(payload.get("status", "PROPOSED")),
            obligations=strs("obligations"),
            assumptions=strs("assumptions"),
            dependencies=strs("dependencies"),
            evidence_required=strs("evidence_required"),
            expected_state_change=payload.get("expected_state_change"),
            failure_condition=strs("failure_condition"),
            parent_question_id=payload.get("parent_question_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def identity_hash(self) -> str:
        body = self.to_dict()
        return stable_hash({k: body[k] for k in IDENTITY_FIELDS})


# --------------------------------------------------------------------------- #
# Scope / universe
# --------------------------------------------------------------------------- #

def scope_semantics(q: Question) -> dict[str, Any]:
    tokens = {t.strip() for t in q.scope.split(",") if t.strip()}
    uncovered = [u for u in q.universe if u not in tokens]
    return {
        "search_scope": q.scope.strip(),
        "declared_universe": q.universe,
        "uncovered_universe_items": uncovered,
        "scope_covers_universe": not uncovered,
        # An absence claim may only be made over a universe the scope covers.
        "absence_claims_allowed": not uncovered,
    }


# --------------------------------------------------------------------------- #
# Assessment
# --------------------------------------------------------------------------- #

@dataclass
class Assessment:
    verdict: str  # PASS | FAIL | BLOCKED
    well_formed: bool
    consumable: bool
    identity_hash: str
    checks: list[Check]
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "well_formed": self.well_formed,
            "consumable": self.consumable,
            "identity_hash": self.identity_hash,
            "blockers": self.blockers,
            "checks": [asdict(c) for c in self.checks],
        }


def assess(q: Question, now: datetime | None = None) -> Assessment:
    """Well-formedness (FAIL) and consumability right now (BLOCKED)."""
    now = now or now_utc()
    checks: list[Check] = []

    def add(cid: str, ok: bool, msg: str, bad: str = "FAIL", **ev: Any) -> None:
        checks.append(Check(cid, "PASS" if ok else bad, msg, ev))

    # -- well-formedness -------------------------------------------------- #
    add("Q-ID-001", bool(QUESTION_ID_RE.match(q.question_id)), "question_id format Q-...", question_id=q.question_id)
    add("Q-ID-002", q.version >= 1, "version >= 1", version=q.version)
    add("Q-SA-001", q.speech_act in VALID_SPEECH_ACTS, "speech act recognized", speech_act=q.speech_act)
    add("Q-REF-001", bool(q.referent.strip()), "referent non-empty")
    add("Q-PROP-001", bool(q.proposition.strip()), "proposition non-empty")
    add("Q-SCOPE-001", bool(q.scope.strip()), "scope non-empty")
    add("Q-UNIV-001", bool(q.universe), "universe declared", universe=q.universe)
    add("Q-AUTH-001", bool(q.authority.get("source")), "authority source present")
    add("Q-CONS-001", bool(q.consumer.get("id")), "consumer identity present")
    add("Q-PURP-001", bool(q.purpose.strip()), "purpose non-empty")
    add("Q-STATUS-001", q.status in VALID_STATUSES, "status recognized", status=q.status)

    effective = parse_ts(q.temporal_validity.get("effective"))
    expires_raw = q.temporal_validity.get("expires")
    expires = parse_ts(expires_raw) if expires_raw is not None else None
    add("Q-TIME-001", effective is not None, "temporal_validity.effective is a valid ISO timestamp",
        effective=q.temporal_validity.get("effective"))
    add("Q-TIME-002", expires_raw is None or expires is not None,
        "temporal_validity.expires is null or a valid ISO timestamp", expires=expires_raw)

    # Universal absence over a partial scope is the false-absence defect class.
    scope = scope_semantics(q)
    absence = bool(ABSENCE_RE.search(q.proposition))
    add("Q-ABS-001", not (absence and not scope["absence_claims_allowed"]),
        "absence proposition requires scope covering the whole declared universe",
        absence_phrasing=absence, uncovered=scope["uncovered_universe_items"])

    # -- consumability right now ------------------------------------------ #
    blockers: list[str] = []
    auth_ok = q.authority.get("status") in CONSUMABLE_AUTHORITY
    add("Q-AUTH-002", auth_ok, "authority status is VALID/ACTIVE", bad="BLOCKED",
        authority_status=q.authority.get("status"))
    if not auth_ok:
        blockers.append("authority not consumable")
    if effective is not None and effective > now:
        checks.append(Check("Q-TIME-003", "BLOCKED", "question not yet effective", {"effective": effective.isoformat(), "now": now.isoformat()}))
        blockers.append("not yet effective")
    elif expires is not None and expires <= now:
        checks.append(Check("Q-TIME-003", "BLOCKED", "question expired", {"expires": expires.isoformat(), "now": now.isoformat()}))
        blockers.append("expired")
    elif effective is not None:
        checks.append(Check("Q-TIME-003", "PASS", "within temporal validity", {"now": now.isoformat()}))
    add("Q-STATUS-002", q.status not in NON_CONSUMABLE_STATUSES, "status permits consumption",
        bad="BLOCKED", status=q.status)
    if q.status in NON_CONSUMABLE_STATUSES:
        blockers.append(f"status {q.status}")

    failed = any(c.status == "FAIL" for c in checks)
    blocked = any(c.status == "BLOCKED" for c in checks)
    verdict = "FAIL" if failed else ("BLOCKED" if blocked else "PASS")
    return Assessment(
        verdict=verdict,
        well_formed=not failed,
        consumable=not failed and not blocked,
        identity_hash=q.identity_hash(),
        checks=checks,
        blockers=blockers,
    )


# --------------------------------------------------------------------------- #
# Identity registry: the same (id, version) must always mean the same question
# --------------------------------------------------------------------------- #

@dataclass
class RegistryResult:
    status: str  # NEW | SAME | NEW_VERSION | CONFLICT | REGRESSION
    detail: str

    @property
    def blocked(self) -> bool:
        return self.status in {"CONFLICT", "REGRESSION"}


class Registry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RegistryError(f"registry {path} is not valid JSON ({exc}); refusing to overwrite it") from exc
            if not isinstance(loaded, dict):
                raise RegistryError(f"registry {path} must be a JSON object; refusing to overwrite it")
            self.entries = loaded

    def register(self, q: Question) -> RegistryResult:
        ident = q.identity_hash()
        prior = self.entries.get(q.question_id)
        if prior is None:
            self.entries[q.question_id] = {"version": q.version, "identity_hash": ident}
            return RegistryResult("NEW", "first registration")
        if q.version < prior["version"]:
            return RegistryResult("REGRESSION", f"version {q.version} < registered {prior['version']}")
        if q.version == prior["version"]:
            if ident == prior["identity_hash"]:
                return RegistryResult("SAME", "identical identity")
            return RegistryResult("CONFLICT", "same id and version, different meaning: material field changed without a new version")
        self.entries[q.question_id] = {"version": q.version, "identity_hash": ident}
        return RegistryResult("NEW_VERSION", f"version {prior['version']} -> {q.version}")

    def save(self) -> None:
        """Atomic: write a temp file in the same directory, then replace, so a crash
        or restart mid-write can never leave a truncated registry."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(self.entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)


# --------------------------------------------------------------------------- #
# Evidence firewall
# --------------------------------------------------------------------------- #

def evidence_firewall(q: Question, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Model proposals, reports and unverified claims never satisfy a requirement."""
    checks: list[Check] = []
    satisfied: dict[str, list[str]] = {}
    for i, rec in enumerate(records, 1):
        cid = f"E-FW-{i:03d}"
        cls = str(rec.get("evidence_class", ""))
        source = rec.get("source_ref")
        if cls not in VALID_EVIDENCE_CLASSES:
            checks.append(Check(cid, "FAIL", "unknown evidence class", {"evidence_class": cls}))
            continue
        if cls in ACCEPTABLE_EVIDENCE and not source:
            checks.append(Check(cid, "FAIL", f"{cls} evidence without source_ref", {}))
            continue
        usable = cls in ACCEPTABLE_EVIDENCE
        checks.append(Check(cid, "PASS", "class/source distinction preserved",
                            {"evidence_class": cls, "usable_as_evidence": usable}))
        if usable:
            for item in rec.get("satisfies", []):
                satisfied.setdefault(str(item), []).append(cid)
    unmet = [req for req in q.evidence_required if req not in satisfied]
    failed = any(c.status == "FAIL" for c in checks)
    if failed:
        verdict = "FAIL"
    elif unmet:
        verdict = "BLOCKED"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "unmet": unmet, "satisfied": satisfied, "checks": [asdict(c) for c in checks]}


# --------------------------------------------------------------------------- #
# Mutation testing of the question itself (applied, not just listed)
# --------------------------------------------------------------------------- #

def mutation_catalog(q: Question) -> list[dict[str, Any]]:
    time_expired = dict(q.temporal_validity)
    time_expired["expires"] = "1900-01-01T00:00:00Z"
    auth_expired = dict(q.authority)
    auth_expired["status"] = "EXPIRED"
    consumer = dict(q.consumer)
    consumer["id"] = "consumer-mutated"
    return [
        {"mutation_id": "MUT-Q-001", "field": "referent", "value": q.referent + " [MUTATED]", "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-002", "field": "proposition", "value": "NOT (" + q.proposition + ")", "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-003", "field": "scope", "value": "OUTSIDE(" + q.scope + ")", "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-004", "field": "temporal_validity", "value": time_expired, "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-005", "field": "authority", "value": auth_expired, "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-006", "field": "consumer", "value": consumer, "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-007", "field": "speech_act", "value": "AUTHORIZATION", "expect": "BLOCKED"},
        {"mutation_id": "MUT-Q-008", "field": "status", "value": "APPROVED", "expect": "DETECTED"},
    ]


def run_mutation_suite(q: Question, now: datetime | None = None) -> dict[str, Any]:
    """Apply each mutation to a copy (same id and version) and push it through the
    production assess() and Registry. Outcomes: DETECTED (malformed), BLOCKED
    (not consumable or identity conflict), PROPAGATED (accepted as the same,
    consumable question - the failure we are looking for)."""
    now = now or now_utc()
    base_assessment = assess(q, now)
    registry = Registry()
    registry.register(q)
    rows = []
    for m in mutation_catalog(q):
        payload = copy.deepcopy(q.to_dict())
        payload[m["field"]] = m["value"]
        try:
            mq = Question.from_dict(payload)
        except QEInputError as exc:
            outcome, why = "DETECTED", str(exc)
        else:
            a = assess(mq, now)
            reg = registry.register(mq)
            if not a.well_formed:
                outcome, why = "DETECTED", "; ".join(c.check_id for c in a.checks if c.status == "FAIL")
            elif not a.consumable:
                outcome, why = "BLOCKED", "; ".join(a.blockers)
            elif reg.blocked:
                outcome, why = "BLOCKED", f"registry {reg.status}: {reg.detail}"
            else:
                outcome, why = "PROPAGATED", "accepted as the same, consumable question"
        rows.append({**{k: m[k] for k in ("mutation_id", "field", "expect")},
                     "outcome": outcome, "why": why, "as_expected": outcome == m["expect"]})
    propagated = [r["mutation_id"] for r in rows if r["outcome"] == "PROPAGATED"]
    return {
        "baseline_verdict": base_assessment.verdict,
        "mutations": rows,
        "propagated": propagated,
        "all_as_expected": all(r["as_expected"] for r in rows),
        "verdict": "PASS" if base_assessment.verdict == "PASS" and not propagated and all(r["as_expected"] for r in rows)
        else ("BLOCKED" if base_assessment.verdict != "PASS" else "FAIL"),
    }


# --------------------------------------------------------------------------- #
# Adversarial inversions (a prompt catalogue; not executable tests)
# --------------------------------------------------------------------------- #

def adversarial_inversions(q: Question) -> list[dict[str, str]]:
    return [
        {"id": "INV-001", "target": "false-positive-success", "question": f"How could '{q.proposition}' appear true while being false?"},
        {"id": "INV-002", "target": "test-target-mismatch", "question": "What if the detector is checking the wrong thing?"},
        {"id": "INV-003", "target": "scope-collapse", "question": "What if the result holds only inside the tested scope but is reported universally?"},
        {"id": "INV-004", "target": "evidence-boundary", "question": "What if a model proposal is being consumed as evidence?"},
        {"id": "INV-005", "target": "authority-leak", "question": "What if the asserting party does not hold the authority it claims?"},
        {"id": "INV-006", "target": "freshness-collapse", "question": "What if the state is stale but treated as current?"},
        {"id": "INV-007", "target": "target-never-exercised", "question": "What if the test passes because the failure never reaches the target?"},
        {"id": "INV-008", "target": "communication-loss", "question": "What can change between producer and consumer?"},
        {"id": "INV-009", "target": "hidden-state", "question": "What hidden state can change the result without appearing in the model?"},
        {"id": "INV-010", "target": "wrong-question", "question": "What if the question itself is wrong or unnecessary?"},
    ]


# --------------------------------------------------------------------------- #
# Self-calibration: controls run through the SAME functions the harness ships
# --------------------------------------------------------------------------- #

CONTROL_QUESTION: dict[str, Any] = {
    "question_id": "Q-CONTROL-001",
    "version": 1,
    "speech_act": "QUESTION",
    "referent": "control referent",
    "proposition": "The control artifact rejects an unclassified row",
    "scope": "control.mjs",
    "universe": ["control.mjs"],
    "authority": {"source": "project-policy", "status": "VALID"},
    "temporal_validity": {"effective": "2026-01-01T00:00:00Z", "expires": None},
    "consumer": {"id": "control-consumer"},
    "purpose": "calibration control",
    "status": "PROPOSED",
}


def calibrate(now: datetime | None = None) -> dict[str, Any]:
    """Run positive and negative controls. `calibrated` is computed, never asserted.
    It certifies this instrument against its own fixtures only: same-author,
    not independent verification."""
    now = now or now_utc()
    controls: list[dict[str, Any]] = []

    def ctl(name: str, expected: str, got: str) -> None:
        controls.append({"control": name, "expected": expected, "got": got, "ok": expected == got})

    base = Question.from_dict(CONTROL_QUESTION)
    ctl("positive: clean question passes", "PASS", assess(base, now).verdict)

    bad_id = dict(CONTROL_QUESTION, question_id="bad")
    ctl("negative: malformed id fails", "FAIL", assess(Question.from_dict(bad_id), now).verdict)

    expired = dict(CONTROL_QUESTION, temporal_validity={"effective": "2026-01-01T00:00:00Z", "expires": "2026-02-01T00:00:00Z"})
    ctl("negative: expired question is blocked", "BLOCKED", assess(Question.from_dict(expired), now).verdict)

    revoked = dict(CONTROL_QUESTION, authority={"source": "project-policy", "status": "REVOKED"})
    ctl("negative: revoked authority is blocked", "BLOCKED", assess(Question.from_dict(revoked), now).verdict)

    partial_absence = dict(CONTROL_QUESTION, proposition="No file named x exists", universe=["control.mjs", "elsewhere"])
    ctl("negative: absence over partial scope fails", "FAIL", assess(Question.from_dict(partial_absence), now).verdict)

    suite = run_mutation_suite(base, now)
    ctl("mutation: 0 of 8 semantic mutations propagate", "0", str(len(suite["propagated"])))

    calibrated = all(c["ok"] for c in controls)
    return {
        "instrument": f"qe-harness {VERSION}",
        "instrument_status": "CALIBRATED" if calibrated else "UNCALIBRATED",
        "independence": "I2-PS (same-author fixtures; not independent verification)",
        "controls": controls,
    }
