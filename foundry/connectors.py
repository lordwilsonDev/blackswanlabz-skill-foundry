"""Read-only connectors; exact resource grants come from operator config, never documents."""

import base64
import json
import os
import re
import urllib.request

from .core import Refused


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refused("connector redirects are forbidden")


def request(url, headers, data=None):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as r:
        raw = r.read(2000001)
        if len(raw) > 2000000:
            raise Refused("source exceeds connector limit")
        return raw, r.headers


def retrieve(grant):
    kind = grant["kind"]
    if kind == "github":
        repo = grant["repo"]
        commit = grant["commit"]
        path = grant["path"]
        if not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo
        ) or not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise Refused("GitHub requires repo and immutable 40-character commit")
        if (
            not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
            or ".." in path.split("/")
            or path.startswith("/")
        ):
            raise Refused("invalid repository path")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "BlackSwanLabz-Foundry",
        }
        token = os.environ.get("FOUNDRY_GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
        raw, _ = request(
            f"https://api.github.com/repos/{repo}/contents/{path}?ref={commit}", headers
        )
        data = json.loads(raw)
        if data.get("encoding") != "base64":
            raise Refused("unsupported GitHub object")
        body = base64.b64decode(data["content"], validate=False).decode("utf-8")
        return {
            "title": path,
            "body": body,
            "locator": f"github:{repo}/{path}",
            "revision": commit,
        }
    if kind == "dropbox":
        token = os.environ.get("FOUNDRY_DROPBOX_TOKEN")
        if not token:
            raise Refused(
                "Dropbox runtime token missing; desktop connector credentials are not exported"
            )
        file_id = grant["file_id"]
        if not re.fullmatch(r"id:[A-Za-z0-9_-]+", file_id):
            raise Refused("exact Dropbox file ID required")
        raw, headers = request(
            "https://content.dropboxapi.com/2/files/download",
            {
                "Authorization": "Bearer " + token,
                "Dropbox-API-Arg": json.dumps({"path": file_id}),
            },
            b"",
        )
        metadata = json.loads(headers["Dropbox-API-Result"])
        if metadata["id"] != file_id or metadata["rev"] != grant["revision"]:
            raise Refused("Dropbox source revision changed")
        return {
            "title": metadata["name"],
            "body": raw.decode("utf-8"),
            "locator": "dropbox:" + file_id,
            "revision": metadata["rev"],
        }
    raise Refused("connector not allowlisted")
