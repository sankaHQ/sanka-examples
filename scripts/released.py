# SPDX-License-Identifier: Apache-2.0
"""Install the verified API prerelease in a fresh public consumer environment."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path

from candidate import CLI_VERSION, IGNORED, Candidate


class Released(Candidate):
    def _setup(self) -> None:
        pins = json.loads(Path(__file__).with_name("api-release.json").read_text())
        revision = pins["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Release catalog must pin an immutable full commit")
        self.revision = revision
        expected = pins["extensions"][self.extension]
        self.env = {
            k: os.environ[k]
            for k in ("PATH", "TMPDIR", "LANG", "SYSTEMROOT", "DEVELOPER_DIR")
            if k in os.environ
        }
        self.env.update(
            UV_NO_CONFIG="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            PYTHONHASHSEED="0",
        )
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "SANKA_HOME"):
            directory = self.root / name.lower()
            directory.mkdir()
            self.env[name] = str(directory)
        shutil.copytree(
            self.example,
            self.project,
            ignore=lambda _p, names: [
                n for n in names if n in IGNORED or n.endswith(".pyc")
            ],
        )
        url = (
            f"https://raw.githubusercontent.com/sankaHQ/extensions/{revision}/"
            f"packages/sanka-extension-{self.extension}/extension.json"
        )
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != expected["manifest_sha256"]:
            raise ValueError("Published manifest digest mismatch")
        manifest = json.loads(raw)
        wheels = {w["name"]: w["sha256"] for w in manifest["wheels"]}
        if wheels != expected["wheels"] or manifest["id"] != f"sanka/{self.extension}":
            raise ValueError("Published wheel closure or identity mismatch")
        self.run("uv", "venv", "--python", "3.12", str(self.root / "cli"))
        self.run(
            "uv",
            "pip",
            "install",
            "--python",
            str(self.root / "cli/bin/python"),
            f"sanka-cli=={CLI_VERSION}",
        )
        self.report.update(
            extension_revision=revision,
            release_tag=pins["tag"],
            release_status="experimental-published",
            manifest_sha256=expected["manifest_sha256"],
            wheels=wheels,
            cli_dependencies=self.run(
                "uv", "pip", "freeze", "--python", str(self.root / "cli/bin/python")
            ).splitlines(),
        )
        self.cli(
            "extension",
            "marketplace",
            "add",
            "https://github.com/sankaHQ/extensions.git",
            "--revision",
            revision,
            "--name",
            "api-converters",
            "--trust",
        )
        self.cli("extension", "add", manifest["id"], "--marketplace", "api-converters")

    def cli(self, *args: str) -> dict:
        command = [*args, "--json"]
        self.report["commands"].append(command)
        result = json.loads(self.run(str(self.root / "cli/bin/sanka"), *command))
        if result.get("outcome") == "error":
            raise RuntimeError(f"CLI reported failure: {result}")
        return result
