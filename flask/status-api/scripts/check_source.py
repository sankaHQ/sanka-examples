# SPDX-License-Identifier: Apache-2.0
"""Check the two documented responses with the actual Flask request client."""

import json
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE / "source"))
from app import app  # noqa: E402


def main():
    observations = []
    with app.test_client() as client:
        for case in json.loads((EXAMPLE / "expected.json").read_text()):
            response = client.open(case["path"], method=case["method"])
            observed = {
                "method": case["method"], "path": case["path"],
                "status": response.status_code, "media_type": response.mimetype,
                "body": response.get_json(),
            }
            if observed != case:
                raise RuntimeError(f"Response differs: {observed!r} != {case!r}")
            observations.append(observed)
    print(json.dumps({"source_checks": "passed", "responses": observations}, indent=2))


if __name__ == "__main__":
    main()
