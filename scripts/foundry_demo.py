"""Run all three modes against seeded repository evidence; never self-approve release."""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.core import Foundry

f = Foundry("runtime")
sources = f.overview("builder", "builder")["sources"]
ids = [s["id"] for s in sources if s["locator"].startswith("github:") and s["active"]]
if not ids:
    raise SystemExit("Retrieve repository sources first")
results = []
for mode in ["methodology", "teaching", "second-brain"]:
    q = {
        "question_id": "Q-DEMO-" + mode,
        "version": 1,
        "speech_act": "QUESTION",
        "referent": "AIL " + mode,
        "proposition": "Identify, invert and test assumptions using repository evidence",
        "scope": ",".join(ids),
        "universe": ids,
        "authority": {"source": "local-operator-demo", "status": "VALID"},
        "temporal_validity": {"effective": "2026-10-18T00:00:00Z", "expires": None},
        "consumer": {"id": "foundry-demo"},
        "purpose": "Reproducible source-grounded " + mode,
        "status": "PROPOSED",
    }
    s = f.assemble("builder", "builder", q, ids, mode)
    r = f.run("builder", "builder", s["id"])
    entry = {
        "mode": mode,
        "skill_id": s["id"],
        "package_sha": s["sha"],
        "status": s["status"],
        "run": r,
    }
    if mode == "teaching":
        entry["diagnostic"] = f.lesson("builder", "builder", s["id"])
        entry["remediation"] = f.lesson("builder", "builder", s["id"], 0, 0.25)
        entry["advance"] = f.lesson("builder", "builder", s["id"], 0, 0.9)
    if mode == "second-brain":
        entry["retrieval"] = f.search("builder", "builder", "inversion assumptions")
    results.append(entry)
Path("reports/end-to-end.json").write_text(
    json.dumps(
        {
            "modes": results,
            "integrity": f.integrity(),
            "release": "CANDIDATE; independent real-world review pending",
        },
        indent=2,
    )
)
samples = []
for _ in range(30):
    start = time.monotonic()
    f.run("builder", "builder", results[0]["skill_id"])
    samples.append((time.monotonic() - start) * 1000)
Path("reports/latency.json").write_text(
    json.dumps(
        {
            "runs": len(samples),
            "source_count": len(ids),
            "p50_ms": statistics.median(samples),
            "p95_ms": sorted(samples)[28],
            "max_ms": max(samples),
            "scope": "serial local workbook executions; not a production load test",
        },
        indent=2,
    )
)
print(
    json.dumps(
        [
            {"mode": x["mode"], "id": x["skill_id"], "status": x["run"]["status"]}
            for x in results
        ]
    )
)
