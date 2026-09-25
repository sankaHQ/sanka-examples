# SPDX-License-Identifier: Apache-2.0
"""Replay HTTP requests against the original FastAPI app and its seeded schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from app import app

cases = json.loads(Path(sys.argv[2]).read_text())
with TestClient(app) as client:
    observed = []
    for case in cases:
        response = client.request(case["method"], case["path"], json=case.get("body"))
        observed.append(
            {
                "status": response.status_code,
                "media_type": response.headers.get("content-type", "").split(";")[0],
                "body": response.json() if response.content else None,
            }
        )
print(json.dumps(observed))
