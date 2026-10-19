"""Local, single-organization skill foundry. Documents remain data, never code."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from registry.registry_tool import find_for

from .vendor.qe.qe import Question, assess
from .vendor.spine import DecisionEvidence, DecisionEvidenceStore

POLICY = "foundry-1"
MODES = {"methodology", "teaching", "second-brain"}
ROLES = {
    "reader": {"read"},
    "builder": {"read", "import", "assemble", "run", "learn"},
    "reviewer": {"read", "review", "promote", "revoke"},
    "operator": {"read", "import", "assemble", "run", "learn", "revoke"},
}


def canonical(x):
    return json.dumps(
        x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class Refused(ValueError):
    pass


def required(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Refused(f"{label} must contain 1–{limit} characters")
    return value.strip()


class Foundry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / "foundry.sqlite3"
        self.spine = DecisionEvidenceStore(str(self.root / "spine.sqlite3"))
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, locator TEXT, revision TEXT, title TEXT, body TEXT, sha TEXT, active INTEGER, imported TEXT, owner TEXT);
            CREATE TABLE IF NOT EXISTS skills(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, name TEXT, version INTEGER, package TEXT, sha TEXT, status TEXT, author TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, skill TEXT, actor TEXT, status TEXT, output TEXT, sha TEXT, created TEXT, duration REAL);
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, skill TEXT, package_sha TEXT, reviewer TEXT, verdict TEXT, rationale TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, actor TEXT, action TEXT, result TEXT, refs TEXT, created TEXT, delivered INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS learners(actor TEXT, skill TEXT, objective INTEGER, attempts INTEGER, score REAL, PRIMARY KEY(actor,skill,objective));
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, actor TEXT, body TEXT, sha TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS questions(id TEXT, version INTEGER, sha TEXT, PRIMARY KEY(id,version));
            """)
        self.flush()

    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    @contextlib.contextmanager
    def transaction(self):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            yield c
        self.flush()

    def event(self, c, actor, action, result, refs=()):
        c.execute(
            "INSERT INTO events(id,actor,action,result,refs,created) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, actor, action, result, canonical(refs), now()),
        )

    def flush(self):
        # Durable outbox: materialize all missing events, including after a crash.
        # BEGIN IMMEDIATE serializes independent Foundry instances.
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for e in c.execute(
                "SELECT * FROM events WHERE delivered=0 ORDER BY seq"
            ).fetchall():
                if not self.spine.trail(e["id"]):
                    self.spine.append(
                        DecisionEvidence(
                            task_id=e["id"],
                            agent_id=e["actor"],
                            policy_version=POLICY,
                            policy_result=e["result"],
                            risk_level="low",
                            selected_action=e["action"],
                            evidence_refs=tuple(json.loads(e["refs"])),
                            timestamp=e["created"],
                        ),
                        audit_seq=e["seq"],
                    )
                c.execute("UPDATE events SET delivered=1 WHERE seq=?", (e["seq"],))

    def authorize(self, actor, role, action):
        required(actor, "actor", 100)
        if action != "read" and not self.integrity()["valid"]:
            raise Refused("evidence integrity failure; mutations disabled")
        if action not in ROLES.get(role, set()):
            with self.transaction() as c:
                self.event(c, actor, action, "DENY")
            raise Refused("permission denied")

    def import_source(self, actor, role, title, body, locator, revision):
        self.authorize(actor, role, "import")
        title = required(title, "title", 200)
        body = required(body, "body", 200000)
        locator = required(locator, "locator", 2000)
        revision = required(revision, "revision", 200)
        sha = digest(body)
        sid = digest([locator, revision, sha])
        with self.transaction() as c:
            previous = c.execute(
                "SELECT * FROM sources WHERE locator=? AND active=1", (locator,)
            ).fetchall()
            for old in previous:
                if old["id"] != sid:
                    c.execute("UPDATE sources SET active=0 WHERE id=?", (old["id"],))
                    self.invalidate(c, old["id"])
            existing = c.execute(
                "SELECT active FROM sources WHERE id=?", (sid,)
            ).fetchone()
            if existing and not existing["active"]:
                raise Refused("revoked source cannot be silently reactivated")
            c.execute(
                "INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?)",
                (sid, locator, revision, title, body, sha, 1, now(), actor),
            )
            self.event(c, actor, "import", "ALLOW", [sid, sha])
        return {
            "id": sid,
            "sha": sha,
            "origin": "operator-import",
            "authenticity": "not independently authenticated",
        }

    def invalidate(self, c, sid):
        for row in c.execute("SELECT id,package FROM skills").fetchall():
            if any(s["id"] == sid for s in json.loads(row["package"])["sources"]):
                c.execute("UPDATE skills SET status='STALE' WHERE id=?", (row["id"],))

    def revoke(self, actor, role, source_id):
        self.authorize(actor, role, "revoke")
        with self.transaction() as c:
            if not c.execute(
                "SELECT id FROM sources WHERE id=?", (source_id,)
            ).fetchone():
                raise Refused("unknown source")
            c.execute("UPDATE sources SET active=0 WHERE id=?", (source_id,))
            self.invalidate(c, source_id)
            self.event(c, actor, "revoke", "ALLOW", [source_id])
        return {"status": "REVOKED"}

    def search(self, actor, role, query):
        self.authorize(actor, role, "read")
        query = required(query, "query")
        tokens = set(re.findall(r"\w{3,}", query.lower()))
        with self.connect() as c:
            rows = c.execute("SELECT * FROM sources WHERE active=1").fetchall()
        hits = []
        for r in rows:
            if digest(r["body"]) != r["sha"]:
                raise Refused("source integrity failure")
            lines = r["body"].splitlines()
            matches = [
                (sum(t in line.lower() for t in tokens), i, line)
                for i, line in enumerate(lines, 1)
            ]
            matches = sorted((x for x in matches if x[0]), reverse=True)[:4]
            if matches:
                hits.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "locator": r["locator"],
                        "revision": r["revision"],
                        "sha": r["sha"],
                        "score": sum(x[0] for x in matches),
                        "excerpts": [
                            {"line": i, "text": line[:2000]} for _, i, line in matches
                        ],
                        "evidence_class": "REPORTED",
                        "warning": "retrieved text is evidence of source content, not proof of truth",
                    }
                )
        return sorted(hits, key=lambda h: (-h["score"], h["id"]))[:12]

    def assemble(self, actor, role, question, source_ids, mode="methodology", name=""):
        self.authorize(actor, role, "assemble")
        if mode not in MODES:
            raise Refused("unsupported mode")
        if (
            not isinstance(source_ids, list)
            or not 1 <= len(source_ids) <= 12
            or any(not isinstance(x, str) for x in source_ids)
        ):
            raise Refused("select 1–12 source IDs")
        q = Question.from_dict(question)
        assessment = assess(q, datetime.now(timezone.utc)).to_dict()
        if not assessment["consumable"]:
            raise Refused("question gate: " + assessment["verdict"])
        if set(q.universe) != set(source_ids) or set(q.scope.split(",")) != set(
            source_ids
        ):
            raise Refused("question scope must match selected source IDs")
        # Supplied question authority describes intent, never grants API authority.
        for check in assessment["checks"]:
            check.get("evidence", {}).pop("now", None)
        name = required(name or q.referent, "name", 150)
        with self.transaction() as c:
            prior = c.execute(
                "SELECT * FROM questions WHERE id=? ORDER BY version DESC LIMIT 1",
                (q.question_id,),
            ).fetchone()
            if prior and (
                q.version < prior["version"]
                or (
                    q.version == prior["version"]
                    and assessment["identity_hash"] != prior["sha"]
                )
            ):
                raise Refused("question identity conflict; increment version")
            c.execute(
                "INSERT OR IGNORE INTO questions VALUES(?,?,?)",
                (q.question_id, q.version, assessment["identity_hash"]),
            )
            sources = []
            steps = []
            for sid in sorted(set(source_ids)):
                s = c.execute(
                    "SELECT * FROM sources WHERE id=? AND active=1", (sid,)
                ).fetchone()
                if not s or digest(s["body"]) != s["sha"]:
                    raise Refused("source unavailable or corrupt")
                sources.append(
                    {k: s[k] for k in ("id", "locator", "revision", "title", "sha")}
                )
                # Bounded, extractive compilation. No document text is interpreted as an instruction to tools.
                for line_no, line in enumerate(s["body"].splitlines(), 1):
                    if (
                        re.match(r"^\s*(?:[-*] |\d+[.)] |#{1,4} )", line)
                        and line.strip()
                    ):
                        steps.append(
                            {
                                "source": sid,
                                "line": line_no,
                                "text": line.strip()[:2000],
                            }
                        )
                        if sum(x["source"] == sid for x in steps) >= 24:
                            break
            if not steps:
                raise Refused(
                    "no structured methodology; supply reviewed headings or steps"
                )
            package = {
                "schema": 1,
                "mode": mode,
                "name": name,
                "question": question,
                "question_assessment": assessment,
                "sources": sources,
                "steps": steps,
                "capabilities": ["read-selected-sources", "render-grounded-workbook"],
                "forbidden": [
                    "shell",
                    "network",
                    "filesystem-write",
                    "external-actions",
                ],
                "coverage": "extractive workbook from selected, revision-pinned documents; no factual adjudication",
                "experts": ["provenance", "scope", "safety", "coverage"],
                "extractor": "structured-lines-v1",
                "upstream_capability": find_for(q.proposition),
                "verification_basis": "deterministic structural checks, not independent domain validation",
            }
            sha = digest(package)
            fp = digest(
                {
                    "name": name,
                    "mode": mode,
                    "sources": sources,
                    "steps": steps,
                    "proposition": q.proposition,
                    "scope": q.scope,
                    "purpose": q.purpose,
                    "authority": q.authority,
                    "expires": q.temporal_validity.get("expires"),
                    "consumer": q.consumer,
                    "extractor": package["extractor"],
                }
            )
            old = c.execute(
                "SELECT * FROM skills WHERE fingerprint=?", (fp,)
            ).fetchone()
            if old:
                self.event(c, actor, "reuse", "ALLOW", [old["id"]])
                return self.skill_dict(old)
            version = c.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM skills WHERE name=?", (name,)
            ).fetchone()[0]
            sid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    sid,
                    fp,
                    name,
                    version,
                    canonical(package),
                    sha,
                    "CANDIDATE",
                    actor,
                    now(),
                ),
            )
            self.event(c, actor, "assemble", "ALLOW", [sid, sha])
        return self.get_skill(sid)

    def skill_dict(self, row):
        d = dict(row)
        d["package"] = json.loads(d["package"])
        return d

    def get_skill(self, sid):
        with self.connect() as c:
            r = c.execute("SELECT * FROM skills WHERE id=?", (sid,)).fetchone()
        if not r:
            raise Refused("unknown skill")
        if digest(json.loads(r["package"])) != r["sha"]:
            raise Refused("package integrity failure")
        return self.skill_dict(r)

    def verify(self, c, skill):
        p = skill["package"]
        findings = []
        if digest(p) != skill["sha"]:
            raise Refused("package integrity failure")
        for src in p["sources"]:
            s = c.execute("SELECT * FROM sources WHERE id=?", (src["id"],)).fetchone()
            if (
                not s
                or not s["active"]
                or s["sha"] != src["sha"]
                or digest(s["body"]) != s["sha"]
            ):
                findings.append(
                    {"expert": "provenance", "verdict": "BLOCK", "source": src["id"]}
                )
                continue
            lines = s["body"].splitlines()
            for step in [x for x in p["steps"] if x["source"] == src["id"]]:
                i = step["line"] - 1
                if not 0 <= i < len(lines) or lines[i].strip()[:2000] != step["text"]:
                    findings.append(
                        {
                            "expert": "provenance",
                            "verdict": "BLOCK",
                            "reason": "citation mismatch",
                        }
                    )
        if not assess(
            Question.from_dict(p["question"]), datetime.now(timezone.utc)
        ).consumable:
            findings.append(
                {
                    "expert": "scope",
                    "verdict": "BLOCK",
                    "reason": "question no longer consumable",
                }
            )
        if p["capabilities"] != ["read-selected-sources", "render-grounded-workbook"]:
            findings.append({"expert": "safety", "verdict": "BLOCK"})
        if not p["steps"] or p["mode"] not in MODES:
            findings.append({"expert": "coverage", "verdict": "BLOCK"})
        for expert in p["experts"]:
            if not any(x["expert"] == expert for x in findings):
                findings.append(
                    {"expert": expert, "verdict": "PASS", "basis": "deterministic"}
                )
        return findings

    def run(self, actor, role, skill_id):
        self.authorize(actor, role, "run")
        started = time.monotonic()
        with self.transaction() as c:
            row = c.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if not row:
                raise Refused("unknown skill")
            skill = self.skill_dict(row)
            findings = self.verify(c, skill)
            blocked = skill["status"] in {"STALE", "REVOKED"} or any(
                x["verdict"] == "BLOCK" for x in findings
            )
            if blocked:
                output = {"status": "BLOCKED", "experts": findings}
            else:
                from .sandbox import execute

                output = execute(skill["package"])
                output["experts"] = findings
            rid = uuid.uuid4().hex
            status = output["status"]
            sha = digest(output)
            c.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                (
                    rid,
                    skill_id,
                    actor,
                    status,
                    canonical(output),
                    sha,
                    now(),
                    time.monotonic() - started,
                ),
            )
            self.event(
                c,
                actor,
                "sandbox-execute",
                "DENY" if status != "PASS" else "ALLOW",
                [rid, skill_id, skill["sha"], sha],
            )
        return {
            "id": rid,
            "skill_id": skill_id,
            "status": status,
            "output": output,
            "sha": sha,
            "production_approved": skill["status"] == "RELEASED",
        }

    def review(self, actor, role, skill_id, verdict, rationale):
        self.authorize(actor, role, "review")
        rationale = required(rationale, "review rationale", 4000)
        if verdict not in {"APPROVE", "REJECT"}:
            raise Refused("invalid verdict")
        with self.transaction() as c:
            s = c.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if not s:
                raise Refused("unknown skill")
            if actor == s["author"]:
                raise Refused("author cannot approve their own package")
            if s["status"] in {"STALE", "REVOKED"}:
                raise Refused("stale skill cannot be reviewed")
            rid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?,?)",
                (rid, skill_id, s["sha"], actor, verdict, rationale, now()),
            )
            if verdict == "REJECT":
                c.execute(
                    "UPDATE skills SET status='CANDIDATE' WHERE id=?", (skill_id,)
                )
            self.event(
                c,
                actor,
                "review",
                "ALLOW",
                [skill_id, rid, s["sha"], digest(rationale)],
            )
        return {"id": rid, "verdict": verdict}

    def promote(self, actor, role, skill_id):
        self.authorize(actor, role, "promote")
        with self.transaction() as c:
            row = c.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if not row:
                raise Refused("unknown skill")
            s = self.skill_dict(row)
            if s["status"] in {"STALE", "REVOKED"} or any(
                x["verdict"] == "BLOCK" for x in self.verify(c, s)
            ):
                raise Refused("verification blocked")
            review = c.execute(
                "SELECT * FROM reviews WHERE skill=? AND package_sha=? ORDER BY rowid DESC LIMIT 1",
                (skill_id, s["sha"]),
            ).fetchone()
            run = c.execute(
                "SELECT * FROM runs WHERE skill=? ORDER BY rowid DESC LIMIT 1",
                (skill_id,),
            ).fetchone()
            if (
                not review
                or review["verdict"] != "APPROVE"
                or review["reviewer"] == s["author"]
            ):
                raise Refused("independent approval required")
            if (
                not run
                or run["status"] != "PASS"
                or digest(json.loads(run["output"])) != run["sha"]
            ):
                raise Refused("passing sandbox receipt required")
            c.execute("UPDATE skills SET status='RELEASED' WHERE id=?", (skill_id,))
            self.event(
                c,
                actor,
                "promote",
                "ALLOW",
                [skill_id, s["sha"], review["id"], run["id"]],
            )
        return self.get_skill(skill_id)

    def lesson(self, actor, role, skill_id, objective=None, score=None):
        self.authorize(actor, role, "learn")
        skill = self.get_skill(skill_id)
        if skill["package"]["mode"] != "teaching":
            raise Refused("not a teaching skill")
        with self.transaction() as c:
            if skill["status"] in {"STALE", "REVOKED"} or any(
                f["verdict"] == "BLOCK" for f in self.verify(c, skill)
            ):
                raise Refused("stale teaching material")
            steps = skill["package"]["steps"]
            if score is not None:
                if (
                    type(objective) != int
                    or not 0 <= objective < len(steps)
                    or type(score) not in (int, float)
                    or not math.isfinite(score)
                    or not 0 <= score <= 1
                ):
                    raise Refused("objective and score out of range")
                c.execute(
                    "INSERT INTO learners VALUES(?,?,?,?,?) ON CONFLICT(actor,skill,objective) DO UPDATE SET attempts=attempts+1,score=excluded.score",
                    (actor, skill_id, objective, 1, score),
                )
                self.event(
                    c,
                    actor,
                    "learner-self-assessment",
                    "ALLOW",
                    [skill_id, str(objective), str(score)],
                )
            progress = {
                r["objective"]: dict(r)
                for r in c.execute(
                    "SELECT * FROM learners WHERE actor=? AND skill=?",
                    (actor, skill_id),
                )
            }
            index = next(
                (
                    i
                    for i in range(len(steps))
                    if progress.get(i, {}).get("score", 0) < 0.8
                ),
                None,
            )
            if index is None:
                return {
                    "status": "SELF_ASSESSED_COMPLETE",
                    "progress": progress,
                    "credential": False,
                }
            step = steps[index]
            attempts = progress.get(index, {}).get("attempts", 0)
            return {
                "status": "PRACTICE",
                "objective": index,
                "material": step,
                "level": "guided" if attempts else "diagnostic",
                "exercise": (
                    "Explain this source passage in your own words, identify an assumption, and give a counterexample."
                    if not attempts
                    else "Break the passage into individual claims. For each claim, state its evidence and one way it could fail."
                ),
                "rubric": [
                    "accurate paraphrase",
                    "source citation",
                    "testable counterexample",
                ],
                "assessment_basis": "learner self-report, not verified mastery",
                "progress": progress,
            }

    def assist(self, actor, role, query, mode, model):
        self.authorize(actor, role, "assemble")
        sources = self.search(actor, role, query)
        if not sources:
            raise Refused("no relevant authorized sources")
        from .model import propose

        result = propose(model, query, sources, mode)
        with self.transaction() as c:
            for src in sources:
                row = c.execute(
                    "SELECT * FROM sources WHERE id=? AND active=1", (src["id"],)
                ).fetchone()
                if (
                    not row
                    or row["sha"] != src["sha"]
                    or digest(row["body"]) != src["sha"]
                ):
                    raise Refused("source changed during model inference")
            pid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO proposals VALUES(?,?,?,?,?)",
                (pid, actor, canonical(result), digest(result), now()),
            )
            self.event(c, actor, "model-proposal", "REVIEW", [pid, digest(result)])
        return {"id": pid, **result}

    def overview(self, actor, role):
        self.authorize(actor, role, "read")
        with self.connect() as c:
            return {
                "sources": [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,title,locator,revision,active,sha FROM sources"
                    )
                ],
                "skills": [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,name,version,status,author,sha FROM skills ORDER BY created DESC"
                    )
                ],
                "runs": [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,skill,status,sha,duration FROM runs ORDER BY created DESC LIMIT 50"
                    )
                ],
                "spine": self.spine.verify_chain(),
                "readiness": "LOCAL_VALIDATION_ONLY",
            }

    def integrity(self):
        self.flush()
        errors = []
        chain = self.spine.verify_chain()
        if not chain["valid"]:
            errors.append("spine hash chain invalid")
        with self.connect() as c:
            for r in c.execute("SELECT * FROM events"):
                trail = self.spine.trail(r["id"])
                if len(trail) != 1 or trail[0].audit_seq != r["seq"]:
                    errors.append("outbox reconciliation failure")
                elif (
                    trail[0].evidence.agent_id != r["actor"]
                    or trail[0].evidence.selected_action != r["action"]
                    or trail[0].evidence.policy_result != r["result"]
                    or sorted(trail[0].evidence.evidence_refs)
                    != sorted(json.loads(r["refs"]))
                ):
                    errors.append("event/spine disagreement")
            for r in c.execute("SELECT * FROM sources"):
                if digest(r["body"]) != r["sha"]:
                    errors.append("source corrupt:" + r["id"])
            for r in c.execute("SELECT * FROM skills"):
                if digest(json.loads(r["package"])) != r["sha"]:
                    errors.append("skill corrupt:" + r["id"])
            for r in c.execute("SELECT * FROM runs"):
                if digest(json.loads(r["output"])) != r["sha"]:
                    errors.append("run corrupt:" + r["id"])
        return {
            "valid": not errors,
            "errors": errors,
            "spine": chain,
            "authenticity": "local hash integrity; external anchoring required",
        }
