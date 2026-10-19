"""Executable deployment gate. Unknown production evidence is never a pass."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.core import Foundry
from foundry.sandbox import execute

p = argparse.ArgumentParser()
p.add_argument("--root", required=True)
p.add_argument("--production", action="store_true")
a = p.parse_args()
checks = {
    "evidence_integrity": Foundry(a.root).integrity()["valid"],
    "sandbox_execution": execute(
        {
            "mode": "methodology",
            "steps": [],
            "question": {"proposition": "probe"},
            "coverage": "probe",
        }
    )["status"]
    == "PASS",
}
blockers = [
    "independent domain acceptance review and held-out model evals not supplied",
    "live model generation has not been demonstrated",
    "multi-user identity/tenant isolation and remote TLS deployment not implemented",
    "external receipt anchoring and off-host backup/restore exercise not demonstrated",
    "Linux container build and image vulnerability scan not executed on this host",
    "sustained-load/SLO and alert-delivery tests not demonstrated",
]
print(
    json.dumps(
        {
            "checks": checks,
            "local_ready": all(checks.values()),
            "production_ready": False,
            "blockers": blockers,
        },
        indent=2,
    )
)
raise SystemExit(2 if a.production else (0 if all(checks.values()) else 1))
