# SPDX-License-Identifier: Apache-2.0
"""Replay the published Go converter against this disposable SQLite example."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE.parents[1] / "scripts"))
from candidate import Published

REVISION = "273175bb3778f8355f2590ceedde0eb72863f113"
TAG = "api-converters-v0.1.0a13"
CONFIG = json.dumps(
    {
        "source_framework": "fastapi",
        "source_file": "app.py",
        "models_file": "models.py",
        "source_database": "sqlite",
        "database_layer": "sqlite",
    }
)


def hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file() and not {".sanka", ".venv", "__pycache__"}.intersection(p.parts)
    }


def accept(router: str, cli_version: str) -> dict:
    with Published(
        example=EXAMPLE / "source",
        extension="python-to-golang",
        packages=[],
        targets=[router],
        match_file="app.py",
        revision=REVISION,
        release_tag=TAG,
        cli_version=cli_version,
    ) as consumer:
        python = consumer.root / "source-env/bin/python"
        consumer.run("uv", "venv", "--python", "3.12", str(python.parent.parent))
        consumer.run(
            "uv", "pip", "install", "--python", str(python), "-r", "requirements.txt"
        )
        consumer.env.update(
            SANKA_GO_SOURCE_PYTHON=str(python), GOMAXPROCS="2", GOFLAGS="-p=2"
        )
        before = hashes(consumer.project)
        forwarded = [
            "--extension-env",
            "SANKA_GO_SOURCE_PYTHON",
            "--extension-env",
            "GOMAXPROCS",
            "--extension-env",
            "GOFLAGS",
        ]
        stages = {}
        for stage in ("scan", "plan"):
            args = [stage, ".", "--extension-config", CONFIG]
            if stage == "plan":
                args += ["--to", router, "--all-endpoints"]
            stages[stage] = consumer.cli(*args, *forwarded)
            assert stages[stage]["outcome"] == "success", stages[stage]
        assert not stages["plan"]["data"]["capture"]["gaps"]
        stages["apply"] = consumer.cli(
            "apply",
            "--root",
            ".",
            "--plan-hash",
            stages["plan"]["data"]["plan_hash"],
            *forwarded,
        )
        for stage in ("test", "verify"):
            stages[stage] = consumer.cli(stage, ".", *forwarded)
            assert (
                stages[stage]["outcome"] == "success"
                and stages[stage]["data"]["ok"] is True
            ), stages[stage]
        assert hashes(consumer.project) == before
        output = consumer.project / ".sanka/extensions/sanka/python-to-golang/golang"
        return {
            "status": "passed_within_scope",
            "candidate": consumer.report,
            "stages": stages,
            "source_preserved": True,
            "source_sha256": before,
            "generated_sha256": hashes(output),
            "scope": "Four write endpoints; 16 ordered HTTP requests and captured SQLite data/identity/rollback parity.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--router", choices=("fiber", "chi", "mux", "gin"), default="fiber"
    )
    parser.add_argument("--cli-version", default="0.3.4")
    parser.add_argument(
        "--report", type=Path, default=EXAMPLE / ".sanka/acceptance.json"
    )
    args = parser.parse_args()
    report = accept(args.router, args.cli_version)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{args.router}: published Scan/Plan/Apply/Test/Verify passed")
