import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROFILE = "(version 1)(deny default)(allow process*)(allow file-read*)(allow sysctl-read)(allow mach-lookup)"


def execute(package):
    worker = Path(__file__).with_name("worker.py").resolve()
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        command = [
            "/usr/bin/sandbox-exec",
            "-p",
            PROFILE,
            sys.executable,
            "-I",
            "-S",
            str(worker),
        ]
        backend = "macos-seatbelt"
    elif shutil.which("docker") and os.environ.get(
        "FOUNDRY_WORKER_IMAGE", ""
    ).startswith("sha256:"):
        command = [
            shutil.which("docker"),
            "run",
            "--rm",
            "-i",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=16",
            "--memory=128m",
            "--cpus=.5",
            "--user=65534:65534",
            os.environ["FOUNDRY_WORKER_IMAGE"],
        ]
        backend = "docker-no-network"
    else:
        return {
            "status": "BLOCKED",
            "reason": "OS sandbox unavailable; refusing host fallback",
        }
    try:
        r = subprocess.run(
            command,
            input=json.dumps(package),
            text=True,
            capture_output=True,
            timeout=8,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "LANG": "C.UTF-8"},
        )
        if r.returncode:
            return {
                "status": "BLOCKED",
                "reason": "sandbox failed",
                "backend": backend,
                "exit_code": r.returncode,
            }
        if len(r.stdout) > 800000:
            return {"status": "BLOCKED", "reason": "output limit"}
        out = json.loads(r.stdout)
        if (
            not isinstance(out, dict)
            or out.get("status") != "PASS"
            or out.get("workbook") != package["steps"]
            or out.get("mode") != package["mode"]
            or out.get("side_effects") != []
        ):
            return {
                "status": "BLOCKED",
                "reason": "worker result failed independent comparison",
            }
        out["sandbox"] = backend
        return out
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return {
            "status": "BLOCKED",
            "reason": "sandbox timeout or invalid output",
            "backend": backend,
        }
