# SPDX-License-Identifier: Apache-2.0
"""Qualify immutable Java candidate wheels through the installed public CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

from candidate import Candidate, sha

ENV_NAMES = (
    "SANKA_JAVA_REPLAY",
    "SANKA_JAVA_MAVEN",
    "SANKA_JAVA_MAVEN_REPO",
    "SANKA_JAVA_PYTHON",
    "JAVA_HOME",
    "SANKA_JAVA_POSTGRES_CONFIG",
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
    def __init__(self, example: Path, bundle: Path, revision: str):
        super().__init__(
            example / "source",
            "java-to-python",
            [],
            ["python-fastapi"],
            "pom.xml",
            revision,
            "0.3.9",
        )
        self.example_root = example
        self.extension_version = "0.1.0a2"
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
        if (
            manifest["id"] != "sanka/java-to-python"
            or manifest["version"] != self.extension_version
        ):
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

    @contextmanager
    def native_database(self):
        schema = self.example_root / "schema.sql"
        if not schema.exists():
            yield {}
            return
        config_path = Path(self.env["SANKA_JAVA_POSTGRES_CONFIG"])
        if (
            not config_path.is_absolute()
            or config_path.is_symlink()
            or config_path.stat().st_mode & 0o077
        ):
            raise ValueError(
                "native fixture connection must be a private absolute file"
            )
        config = json.loads(config_path.read_text())
        if config["host"] != "127.0.0.1" or config["database"] != "postgres":
            raise ValueError("native tests require a local fixture server")

        def sql(database, statement):
            return self.run(
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-p",
                str(config["port"]),
                "-U",
                config["user"],
                "-d",
                database,
                "-Atqc",
                statement,
                env=self.env
                | {
                    "PGPASSWORD": config["password"],
                    "PGCONNECT_TIMEOUT": "5",
                    "PGSSLMODE": "disable",
                },
            ).strip()

        if sql("postgres", "SHOW server_version_num") != "170011":
            raise ValueError("native fixture requires PostgreSQL 17.11")
        name = "sanka_java_" + uuid.uuid4().hex
        sql(
            "postgres", f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8'"
        )
        try:
            sql(name, schema.read_text())
            yield {
                "SANKA_JAVA_DATABASE_URL": f"jdbc:postgresql://127.0.0.1:{config['port']}/{name}",
                "SANKA_JAVA_DATABASE_USER": config["user"],
                "SANKA_JAVA_DATABASE_PASSWORD": config["password"],
            }
        finally:
            sql("postgres", f'DROP DATABASE "{name}" WITH (FORCE)')

    def source_tests(self) -> int:
        with self.native_database() as database_env:
            return self._source_tests(database_env)

    def _source_tests(self, database_env: dict) -> int:
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
            env=self.env | database_env,
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


def compare_evidence(actual: dict, recorded: dict) -> None:
    # This diagnostic covers every artifact in a user's Maven cache, including
    # unrelated cached dependencies. All portable acceptance fields must match.
    diagnostic = {"source_dependencies"}
    left = {key: value for key, value in actual.items() if key not in diagnostic}
    right = {key: value for key, value in recorded.items() if key not in diagnostic}
    if json.dumps(left, sort_keys=True, allow_nan=False) != json.dumps(
        right, sort_keys=True, allow_nan=False
    ):
        raise ValueError(
            "fresh acceptance differs from committed evidence; review and regenerate the receipt"
        )


def qualify(
    example: Path, bundle: Path, revision: str, check_evidence: bool = False
) -> None:
    crud = example.name == "order-api"
    case_count = len(
        json.loads((example / "source/sanka-verify.json").read_text())["scenarios"]
    )
    if os.environ.get("SANKA_JAVA_REPLAY") != "1":
        raise ValueError(
            "set SANKA_JAVA_REPLAY=1 to execute this trusted synthetic example"
        )
    output = example / ".sanka"
    if output.is_symlink():
        raise ValueError("example output must not be a symlink")
    output.mkdir(exist_ok=True)
    destination = output / "evidence.json"
    destination.unlink(missing_ok=True)
    before = hashes(example / "source")
    with JavaCandidate(example, bundle, revision) as candidate:
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
        if report.get("ok") is not True or len(report["steps"]) != case_count:
            raise ValueError("CLI stages lack actual parity evidence")
        generated = artifacts / "python-fastapi"
        generated_hashes = hashes(generated)
        app = generated / "app.py"
        original = app.read_text()
        if crud:
            changed = original.replace(
                "payload = _dump(entity)",
                'payload = _dump(entity)\n        entity.name = "database-only-drift"',
            )
        else:
            changed = original.replace("Hello, ", "Goodbye, ")
        if changed == original:
            raise ValueError("intentional mutation did not change the target")
        app.write_text(changed)
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
        if crud and not any(
            "tables" in str(step["problems"]).lower() for step in mismatch["steps"]
        ):
            raise ValueError("Verify did not identify database-state divergence")
        app.write_text(original)
        if hashes(example / "source") != before or hashes(candidate.project) != before:
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
            "candidate_native_tests": case_count,
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
        if crud:
            receipt.update(
                scope="Flat PostgreSQL CRUD: validated JSON requests, exact string decimals, 200/201/204/400/404/409 responses, persisted rows and identity sequence after all 43 requests, including rollback after flush.",
                unsupported=[
                    "authentication",
                    "authorization",
                    "relationships",
                    "custom queries",
                    "concurrent writes",
                    "live TCP",
                    "production cutover",
                ],
                database_mutation_rejected=True,
                database_runtime="PostgreSQL 17.11",
                native_schema_sha256=sha(example / "schema.sql"),
            )
        destination.write_text(json.dumps(receipt, indent=2) + "\n")
        if check_evidence:
            compare_evidence(
                receipt, json.loads((example / "evidence.json").read_text())
            )
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "cases": case_count,
                    "source_junit": native_count,
                    "intentional_mismatch_rejected": True,
                    "evidence": str(destination),
                },
                indent=2,
            )
        )


def main(example: Path) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--revision")
    parser.add_argument("--check-evidence", action="store_true")
    args = parser.parse_args()
    revision = (
        args.revision
        or json.loads((example / "migration.json").read_text())["destinations"][0][
            "candidate_revision"
        ]
    )
    qualify(example, args.bundle, revision, args.check_evidence)
