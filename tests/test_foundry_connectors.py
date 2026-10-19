import base64
import json
from unittest.mock import patch

import pytest

from foundry.connectors import NoRedirect, retrieve
from foundry.core import Refused


@pytest.mark.parametrize(
    "patches",
    [
        {"repo": "evil.com/o/r"},
        {"commit": "main"},
        {"path": "../secret"},
        {"path": "/secret"},
        {"path": "a?token=bad"},
    ],
)
def test_github_exact_scope(patches):
    grant = {
        "kind": "github",
        "repo": "o/r",
        "commit": "a" * 40,
        "path": "README.md",
        **patches,
    }
    with patch("foundry.connectors.request") as req:
        with pytest.raises(Refused):
            retrieve(grant)
        req.assert_not_called()


def test_github_read_content():
    with patch(
        "foundry.connectors.request",
        return_value=(
            json.dumps(
                {
                    "encoding": "base64",
                    "content": base64.b64encode(b"# Evidence").decode(),
                }
            ).encode(),
            {},
        ),
    ):
        assert (
            retrieve(
                {
                    "kind": "github",
                    "repo": "o/r",
                    "commit": "a" * 40,
                    "path": "README.md",
                }
            )["body"]
            == "# Evidence"
        )


def test_redirect_blocked():
    with pytest.raises(Refused):
        NoRedirect().redirect_request(None, None, None, None, None, None)


def test_dropbox_revision_drift():
    with (
        patch.dict("os.environ", {"FOUNDRY_DROPBOX_TOKEN": "fake"}),
        patch(
            "foundry.connectors.request",
            return_value=(
                b"text",
                {
                    "Dropbox-API-Result": json.dumps(
                        {"id": "id:ABC", "rev": "changed", "name": "x"}
                    )
                },
            ),
        ),
    ):
        with pytest.raises(Refused):
            retrieve({"kind": "dropbox", "file_id": "id:ABC", "revision": "original"})
