# SPDX-License-Identifier: Apache-2.0
"""Replay the checked-in source scenarios against a disposable SQLite file."""

import json
import os
import runpy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

source = Path(__file__).parent / "source"
sys.path.insert(0, str(source))
with TemporaryDirectory(prefix="sanka-widget-source-") as temporary:
    os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(temporary) / "widgets.sqlite3")
    from app import app, engine

    runpy.run_path(str(source.parent / "setup.py"))
    with TestClient(app) as client:
        for case in json.loads((source / "sanka-verify.json").read_text())["scenarios"]:
            response = client.request(
                case["method"],
                case["path"],
                **({"json": case["body"]} if "body" in case else {}),
            )
            assert response.status_code == case["expected_status"], (
                case["id"],
                response.text,
            )
            if case["id"] == "widgets-15":
                assert response.json()["id"] == 1, (
                    "SQLite ROWID allocation follows the remaining rows"
                )
    engine.dispose()
print("16 source scenarios passed, including SQLite identity after deletion")
