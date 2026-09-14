# SPDX-License-Identifier: Apache-2.0
"""Plan a tiny configuration upgrade without modifying application files."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from sanka_extensions.code import (
    ExtensionRequest,
    ExtensionResponse,
    decode_request,
    encode_response,
    failure_response,
    success_response,
)

EXTENSION_ID = "example/config-upgrade"
VERSION = "0.1.0"
LIMITATION = "Teaching example: scan and plan only; no apply, test or verify capability."


def handle(request: ExtensionRequest) -> ExtensionResponse:
    if (request.extension_id, request.extension_version) != (EXTENSION_ID, VERSION):
        return failure_response(
            request, code="EXAMPLE_IDENTITY", message="Wrong extension identity"
        )
    if request.command not in {"scan", "plan"}:
        return failure_response(
            request, code="EXAMPLE_UNSUPPORTED_COMMAND", message="Only scan and plan are supported"
        )
    try:
        root = Path(request.project_root).resolve()
        source = (root / "example-app.json").resolve()
        if not source.is_relative_to(root):
            raise ValueError("example-app.json must stay inside the project")
        original = source.read_bytes()
        config = json.loads(original)
        if (
            not isinstance(config, dict)
            or set(config) != {"schema_version", "title"}
            or type(config["schema_version"]) is not int
            or config["schema_version"] != 1
            or not isinstance(config["title"], str)
            or not config["title"].strip()
        ):
            raise ValueError("Expected schema_version 1 and a non-empty title, with no extra keys")
        digest = hashlib.sha256(original).hexdigest()
        if request.command == "scan":
            return success_response(
                request,
                data={"source": "example-app.json", "source_sha256": digest, "schema_version": 1},
                limitations=[LIMITATION],
            )
        plan = {
            "source": "example-app.json",
            "source_sha256": digest,
            "proposed": {"schema_version": 2, "name": config["title"]},
        }
        encoded = json.dumps(plan, sort_keys=True, indent=2).encode() + b"\n"
        artifacts = Path(request.artifact_root).resolve()
        artifacts.mkdir(parents=True, exist_ok=True)
        output = artifacts / "config-plan.json"
        if output.is_symlink():
            raise ValueError("Plan artifact must not be a symlink")
        output.write_bytes(encoded)
        return success_response(
            request,
            data={"plan_hash": hashlib.sha256(encoded).hexdigest(), "source_sha256": digest},
            artifacts=[str(output)],
            limitations=[LIMITATION],
        )
    except (OSError, ValueError) as error:
        return failure_response(request, code="EXAMPLE_INVALID_INPUT", message=str(error))


def main() -> int:
    try:
        request = decode_request(json.load(sys.stdin))
    except (ValueError, UnicodeError) as error:
        # Without a valid request identity, a correlated response cannot be made.
        print(f"Invalid extension request: {error}", file=sys.stderr)
        return 2
    response = handle(request)
    print(json.dumps(encode_response(response), sort_keys=True))
    return 0 if response.outcome == "success" else 1
