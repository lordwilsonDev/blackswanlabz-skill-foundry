"""Loopback operator service. TLS/auth proxy required for remote deployment."""

import argparse
import hashlib
import hmac
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .connectors import retrieve
from .core import Foundry, Refused, canonical


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root, config):
        self.foundry = Foundry(root)
        self.config = config
        for p in config["principals"]:
            if len(p["token_sha256"]) != 64:
                raise ValueError("token hash required")
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "Foundry/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # do not log tokens, queries, or document content

    def send(self, status, data, ctype="application/json"):
        body = (canonical(data) if ctype == "application/json" else data).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def principal(self):
        token = self.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            raise Refused("authentication required")
        sha = hashlib.sha256(token[7:].encode()).hexdigest()
        for p in self.server.config["principals"]:
            if hmac.compare_digest(sha, p["token_sha256"]):
                return p["id"], p["role"]
        raise Refused("authentication required")

    def do_GET(self):
        try:
            if self.path == "/healthz":
                return self.send(200, {"status": "alive", "production_ready": False})
            if self.path in ("/", "/app.js", "/style.css"):
                name = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/style.css": "style.css",
                }[self.path]
                return self.send(
                    200,
                    (Path(__file__).parent / "ui" / name).read_text(),
                    {
                        "/": "text/html",
                        "/app.js": "text/javascript",
                        "/style.css": "text/css",
                    }[self.path],
                )
            actor, role = self.principal()
            f = self.server.foundry
            if self.path == "/api/overview":
                return self.send(200, f.overview(actor, role))
            if self.path == "/api/integrity":
                f.authorize(actor, role, "read")
                return self.send(200, f.integrity())
            if self.path == "/metrics":
                overview = f.overview(actor, role)
                return self.send(
                    200,
                    "\n".join(
                        f"foundry_{k} {len(overview[k])}"
                        for k in ["sources", "skills", "runs"]
                    )
                    + "\n",
                    "text/plain",
                )
            return self.send(404, {"error": "not found"})
        except Refused as e:
            self.send(403, {"error": str(e)})
        except Exception:
            self.send(500, {"error": "internal error; operator investigation required"})

    def do_POST(self):
        start = time.monotonic()
        actor = "anonymous"
        try:
            # Reject cross-origin browser requests. No cookies, CORS, or URL tokens.
            if (
                self.headers.get("Origin")
                and self.headers["Origin"] != f"http://{self.headers.get('Host')}"
            ):
                raise Refused("cross-origin request rejected")
            actor, role = self.principal()
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 600000:
                return self.send(413, {"error": "request size limit"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "JSON required"})
            p = json.loads(self.rfile.read(length))
            f = self.server.foundry
            if not isinstance(p, dict):
                raise Refused("JSON object required")
            route = self.path
            if route == "/api/import":
                result = f.import_source(actor, role, **p)
            elif route == "/api/retrieve":
                f.authorize(actor, role, "import")
                grant = self.server.config.get("source_grants", {}).get(
                    p.get("grant_id")
                )
                if not grant:
                    raise Refused("resource not authorized")
                result = f.import_source(actor, role, **retrieve(grant))
            elif route == "/api/assist":
                result = f.assist(
                    actor, role, p["query"], p["mode"], self.server.config.get("model")
                )
            elif route == "/api/search":
                result = f.search(actor, role, p["query"])
            elif route == "/api/assemble":
                result = f.assemble(actor, role, **p)
            elif route == "/api/run":
                result = f.run(actor, role, **p)
            elif route == "/api/review":
                result = f.review(actor, role, **p)
            elif route == "/api/promote":
                result = f.promote(actor, role, **p)
            elif route == "/api/revoke":
                result = f.revoke(actor, role, **p)
            elif route == "/api/lesson":
                result = f.lesson(actor, role, **p)
            elif route == "/api/package":
                f.authorize(actor, role, "read")
                result = f.get_skill(p["skill_id"])
            else:
                return self.send(404, {"error": "not found"})
            self.send(200, result)
        except Refused as e:
            try:
                with self.server.foundry.transaction() as c:
                    self.server.foundry.event(
                        c, actor, "api-refusal", "DENY", [self.path.split("?")[0]]
                    )
            except Exception:
                pass
            self.send(403, {"error": str(e)})
        except (ValueError, TypeError, KeyError):
            self.send(400, {"error": "invalid request fields"})
        except Exception:
            self.send(500, {"error": "operation failed; no readiness claim"})
        finally:
            print(
                canonical(
                    {
                        "event": "http_request",
                        "path": self.path.split("?")[0],
                        "duration_ms": round((time.monotonic() - start) * 1000, 2),
                    }
                ),
                flush=True,
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--port", type=int, default=8787)
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text())
    Server(("127.0.0.1", a.port), a.root, config).serve_forever()


if __name__ == "__main__":
    main()
