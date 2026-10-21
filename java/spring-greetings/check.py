# SPDX-License-Identifier: Apache-2.0
"""Qualify immutable Java candidate wheels through the installed public CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candidate import Candidate, sha  # noqa: E402

ENV_NAMES = (
    "SANKA_JAVA_REPLAY",
    "SANKA_JAVA_MAVEN",
    "SANKA_JAVA_MAVEN_REPO",
    "SANKA_JAVA_PYTHON",
    "JAVA_HOME",
)


def hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and not set(p.relative_to(root).parts)
        & {".sanka", "target", "__pycache__", ".pytest_cache", ".venv"}
    }


class JavaCandidate(Candidate):
    def __init__(self, bundle: Path, revision: str):
        super().__init__(
            EXAMPLE / "source",
            "java-to-python",
            [],
            ["python-fastapi"],
            "pom.xml",
            revision,
            "0.3.9",
        )
        self.bundle = bundle.resolve(strict=True)
        provenance = self.bundle / "build-provenance.json"
        if provenance.is_symlink() or not provenance.is_file():
            raise ValueError("candidate bundle lacks regular build provenance")
        record = json.loads(provenance.read_text())
        if (
            record.get("schema") != "sanka.java-candidate-build/v1"
            or record.get("revision") != revision
        ):
            raise ValueError("candidate bundle does not match the pinned revision")
        self.artifacts = record.get("artifacts")
        if not isinstance(self.artifacts, dict) or not self.artifacts:
            raise ValueError("candidate build provenance lacks artifact digests")
        for name, expected in self.artifacts.items():
            path = self.bundle / name
            if (
                Path(name).name != name
                or path.is_symlink()
                or not path.is_file()
                or sha(path) != expected
            ):
                raise ValueError("candidate artifact differs from its recorded build")
        self.report["build_provenance_sha256"] = sha(provenance)

    def _setup(self):
        self._prepare_workspace()
        self.env.update(
            {key: os.environ[key] for key in ENV_NAMES if key in os.environ}
        )
        manifest_path = self.bundle / "sanka-extension-java-to-python.json"
        if self.artifacts.get(manifest_path.name) != sha(manifest_path):
            raise ValueError("candidate manifest is not bound to its build")
        manifest = json.loads(manifest_path.read_text())
        if manifest["id"] != "sanka/java-to-python" or manifest["version"] != "0.1.0a1":
            raise ValueError("candidate extension identity mismatch")
        wheels = self.root / "wheels"
        wheels.mkdir()
        for entry in manifest["wheels"]:
            name = entry["name"]
            path = self.bundle / name
            if (
                Path(name).name != name
                or not name.endswith(".whl")
                or path.is_symlink()
                or sha(path) != entry["sha256"]
                or self.artifacts.get(name) != entry["sha256"]
            ):
                raise ValueError("candidate wheel checksum mismatch")
            shutil.copyfile(path, wheels / name)
        self.report["wheels"] = {p.name: sha(p) for p in sorted(wheels.glob("*.whl"))}
        self._install_cli()
        self._serve_candidate(wheels)

    def cli(self, *args: str) -> dict:
        result = super().cli(*args)
        if result.get("outcome") != "success":
            raise RuntimeError(
                f"CLI did not succeed: {args[0]} ({result.get('outcome')})"
            )
        return result

    def source_tests(self) -> int:
        settings = self.root / "settings.xml"
        settings.write_text(
            '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"/>\n'
        )
        self.run(
            self.env["SANKA_JAVA_MAVEN"],
            "-B",
            "-ntp",
            "--offline",
            "-s",
            str(settings),
            "-gs",
            str(settings),
            "-Dmaven.repo.local=" + self.env["SANKA_JAVA_MAVEN_REPO"],
            "test",
        )
        reports = list(self.project.glob("target/surefire-reports/TEST-*.xml"))
        tests = [
            case for report in reports for case in ET.parse(report).findall("testcase")
        ]
        if len(tests) != 3 or any(
            case.find(tag) is not None
            for case in tests
            for tag in ("failure", "error", "skipped")
        ):
            raise ValueError("source JUnit tests failed, skipped or were missing")
        return len(tests)


def qualify(bundle: Path, revision: str) -> None:
    if os.environ.get("SANKA_JAVA_REPLAY") != "1":
        raise ValueError(
            "set SANKA_JAVA_REPLAY=1 to execute this trusted synthetic example"
        )
    output = EXAMPLE / ".sanka"
    if output.is_symlink():
        raise ValueError("example output must not be a symlink")
    output.mkdir(exist_ok=True)
    destination = output / "evidence.json"
    destination.unlink(missing_ok=True)
    before = hashes(EXAMPLE / "source")
    with JavaCandidate(bundle, revision) as candidate:
        native_count = candidate.source_tests()
        env_args = [
            part
            for name in ENV_NAMES
            if name in candidate.env
            for part in ("--extension-env", name)
        ]
        stages = {}
        for stage in ("scan", "plan"):
            args = [stage, str(candidate.project), *env_args]
            if stage == "plan":
                args += ["--to", "python-fastapi"]
            result = candidate.cli(*args)
            stages[stage] = result["outcome"]
        applied = candidate.cli(
            "apply",
            "--root",
            str(candidate.project),
            "--plan-hash",
            result["data"]["plan_hash"],
            *env_args,
        )
        stages["apply"] = applied["outcome"]
        for stage in ("test", "verify"):
            stages[stage] = candidate.cli(stage, str(candidate.project), *env_args)[
                "outcome"
            ]
        artifacts = candidate.project / ".sanka/extensions/sanka/java-to-python"
        report = json.loads((artifacts / "verify.json").read_text())
        if report.get("ok") is not True or len(report["steps"]) != 9:
            raise ValueError("CLI stages lack actual parity evidence")
        generated = artifacts / "python-fastapi"
        generated_hashes = hashes(generated)
        app = generated / "app.py"
        original = app.read_text()
        app.write_text(original.replace("Hello, ", "Goodbye, "))
        try:
            candidate.cli("verify", str(candidate.project), *env_args)
        except RuntimeError:
            mismatch = json.loads((artifacts / "verify.json").read_text())
            if mismatch.get("ok") is not False or not any(
                step["problems"] for step in mismatch["steps"]
            ):
                raise ValueError(
                    "intentional mutation did not produce behavioral differences"
                ) from None
        else:
            raise ValueError("Verify accepted an intentionally changed response")
        app.write_text(original)
        if hashes(EXAMPLE / "source") != before or hashes(candidate.project) != before:
            raise ValueError("qualification changed the source")
        saved = output / "python-fastapi"
        if saved.exists():
            raise ValueError(
                "saved candidate exists; move it before running qualification again"
            )
        shutil.copytree(generated, saved)
        receipt = {
            "status": "passed_within_scope",
            "stages": stages,
            "candidate": {
                key: candidate.report[key]
                for key in (
                    "cli_version",
                    "extension_revision",
                    "extension_id",
                    "sdk_version",
                    "release_status",
                    "wheels",
                    "build_provenance_sha256",
                )
            },
            "source_preserved": True,
            "source_sha256": before,
            "generated_sha256": generated_hashes,
            "source_native_tests": native_count,
            "candidate_native_tests": 9,
            "comparison_cases": len(report["steps"]),
            "transport": report["transport"],
            "source_digest": report["source_digest"],
            "candidate_digest": report["candidate_digest"],
            "scenarios_digest": report["scenarios_digest"],
            "intentional_mismatch_rejected": True,
            "observations": report["candidate_observations"],
            "target_runtime": report["target_runtime"],
            "source_dependencies": {
                key: report["source_runtime"][key]
                for key in ("dependency_digest", "dependency_count")
            },
            "scope": "Three stateless GET routes, string query/path binding, records, null, Unicode and exact int64 JSON. Spring MockMvc compared with FastAPI TestClient.",
            "unsupported": [
                "security",
                "persistence",
                "CRUD",
                "custom services",
                "errors",
                "HEAD/OPTIONS",
                "arbitrary headers",
                "live TCP",
            ],
            "complete_backend": False,
        }
        destination.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "cases": 9,
                    "source_junit": native_count,
                    "intentional_mismatch_rejected": True,
                    "evidence": str(destination),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--revision")
    args = parser.parse_args()
    revision = (
        args.revision
        or json.loads((EXAMPLE / "migration.json").read_text())["destinations"][0][
            "candidate_revision"
        ]
    )
    qualify(args.bundle, revision)
