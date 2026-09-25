# SPDX-License-Identifier: Apache-2.0
"""Exercise the published Python-to-Go wheel against disposable PostgreSQL schemas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql

EXAMPLE = Path(__file__).resolve().parents[1]
REPOSITORY = EXAMPLE.parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
from candidate import Published

RELEASE_TAG = "api-converters-v0.1.0a6"
RELEASE_REVISION = "5b7fdeb80c524d87795ddae75ea356d00cea0d12"
CONFIG = {
    "source_framework": "fastapi",
    "target_framework": "fiber",
    "database_layer": "pgx",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not {".sanka", "__pycache__", ".venv"}.intersection(
            path.relative_to(root).parts
        )
    }


def schema_url(dsn: str, schema: str) -> str:
    parsed = urlsplit(dsn)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "options"]
    query.append(("options", "-csearch_path=" + schema))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def accept(revision: str) -> dict:
    require(
        len(revision) == 40 and all(c in "0123456789abcdef" for c in revision),
        "Pin the published a6 merge commit before running acceptance",
    )
    dsn = os.environ["SANKA_MIGRATE_TEST_POSTGRES_DSN"]
    original = hashes(EXAMPLE / "source")
    with Published(
        example=EXAMPLE / "source",
        extension="python-to-golang",
        packages=[],
        targets=["fiber"],
        match_file="app.py",
        revision=revision,
        release_tag=RELEASE_TAG,
        cli_version="0.3.0",
    ) as consumer:
        project = consumer.project
        source_env = consumer.root / "source-env"
        consumer.run("uv", "venv", "--python", "3.12", str(source_env))
        python = str(source_env / "bin/python")
        consumer.run(
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "-r",
            str(project / "requirements.txt"),
        )
        consumer.env.update(
            SANKA_GO_SOURCE_PYTHON=python,
            GOMAXPROCS="2",
            GOFLAGS="-p=2",
        )
        before = hashes(project)
        schemas = ["example_" + uuid.uuid4().hex for _ in range(2)]
        with psycopg.connect(dsn, autocommit=True) as admin:
            try:
                for schema in schemas:
                    admin.execute(
                        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
                    )
                source_url, target_url = [schema_url(dsn, schema) for schema in schemas]
                consumer.env.update(
                    SANKA_GO_SOURCE_TEST_DATABASE_URL=source_url.replace(
                        "postgresql://", "postgresql+psycopg://", 1
                    ),
                    SANKA_GO_TARGET_TEST_DATABASE_URL=target_url,
                )

                def cli(*args: str) -> dict:
                    forwarded = [
                        part
                        for name in (
                            "SANKA_GO_SOURCE_PYTHON",
                            "SANKA_GO_SOURCE_TEST_DATABASE_URL",
                            "SANKA_GO_TARGET_TEST_DATABASE_URL",
                            "GOMAXPROCS",
                            "GOFLAGS",
                        )
                        for part in ("--extension-env", name)
                    ]
                    return consumer.cli(*args, *forwarded)

                config = json.dumps(CONFIG)
                scan = cli("scan", ".", "--extension-config", config)
                require(scan["outcome"] == "success", "Scan failed")
                plan = cli("plan", ".", "--to", "fiber", "--extension-config", config)[
                    "data"
                ]
                require(
                    plan["capture"]["generation_ready"] and not plan["capture"]["gaps"],
                    "The source has unsupported conversion gaps",
                )
                require(
                    plan["plan_hash"]
                    == cli("plan", ".", "--to", "fiber", "--extension-config", config)[
                        "data"
                    ]["plan_hash"],
                    "Repeated plan changed",
                )
                require(
                    {"migrations/00001_0001.sql", "migrations/00002_0002.sql"}
                    <= set(plan["files"]),
                    "Two Alembic revisions were not lowered",
                )
                output = project / ".sanka/extensions/sanka/python-to-golang/golang"
                try:
                    cli("apply", "--plan-hash", "sha256:" + "0" * 64)
                except RuntimeError as error:
                    require(
                        "SANKA_EXTENSION_PLAN_HASH_MISMATCH" in str(error),
                        "Wrong plan hash failed for an unexpected reason",
                    )
                else:
                    raise RuntimeError("Apply accepted an unreviewed plan hash")
                require(not output.exists(), "Rejected apply created a destination")
                applied = cli("apply", "--plan-hash", plan["plan_hash"])
                generated = hashes(output)
                require(
                    generated
                    == {
                        name: hashlib.sha256(content.encode()).hexdigest()
                        for name, content in plan["files"].items()
                    },
                    "Generated files differ from the reviewed plan",
                )
                tested = cli("test")
                require(tested["data"]["ok"], "CLI test did not pass")
                verified = cli("verify")
                result = verified["data"]
                require(
                    result["ok"] and result["source"] == result["candidate"],
                    "Source and generated Go behavior differ",
                )
                require(
                    result["qualification"]["source_compared"],
                    "Verify did not compare the source",
                )
                require(
                    all(
                        "tables" in row and "sequences" in row
                        for row in result["candidate"]
                    ),
                    "Verify omitted PostgreSQL state",
                )
                indexes = [
                    admin.execute(
                        "SELECT tablename,indexname FROM pg_indexes WHERE schemaname=%s "
                        "AND indexname NOT LIKE '%%_pkey' ORDER BY tablename,indexname",
                        (schema,),
                    ).fetchall()
                    for schema in schemas
                ]
                require(indexes[0] == indexes[1], "Source and Go indexes differ")
                compilers = sorted((project / ".sanka/go-toolchain").glob("**/bin/go"))
                go = (
                    str(compilers[0])
                    if compilers
                    else shutil.which("go", path=consumer.env["PATH"])
                )
                require(go is not None, "Qualified Go compiler missing")
                rollback = subprocess.run(
                    [go, "run", "-mod=readonly", "./cmd/migrate", "down"],
                    cwd=output,
                    env=consumer.env
                    | {
                        "DATABASE_URL": target_url,
                        "GOTOOLCHAIN": "local",
                        "GOWORK": "off",
                    },
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                require(rollback.returncode == 0, "Generated Goose rollback failed")
                remaining = admin.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema=%s "
                    "AND table_name IN ('parents','widgets')",
                    (schemas[1],),
                ).fetchone()[0]
                require(remaining == 0, "Rollback left application tables behind")
                require(
                    hashes(project) == before
                    and hashes(EXAMPLE / "source") == original,
                    "Migration changed source files",
                )
                require(
                    hashes(output) == generated, "Acceptance changed generated files"
                )
                return {
                    "schema": "sanka-examples/acceptance/v1",
                    "example": "fastapi/relational-widgets",
                    "outcome": "passed",
                    "candidate": consumer.report,
                    "source_sha256": original,
                    "generated_sha256": generated,
                    "source_preserved": True,
                    "repeated_plan_identical": True,
                    "wrong_plan_rejected": True,
                    "reviewed_core_plan_hash": plan["plan_hash"],
                    "extension_plan_hash": plan["extension"]["plan_hash"],
                    "stages": {
                        "scan": scan["outcome"],
                        "plan": "success",
                        "apply": applied["outcome"],
                        "test": tested["outcome"],
                        "verify": verified["outcome"],
                    },
                    "postgresql_indexes_equal": True,
                    "rollback_tables_removed": True,
                    "scenarios_compared": len(result["candidate"]),
                    "unsupported": [
                        "Alembic branches and schema alterations",
                        "Application data transfer",
                        "Production deployment",
                    ],
                }
            finally:
                for schema in schemas:
                    admin.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(schema)
                        )
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=RELEASE_REVISION)
    args = parser.parse_args()
    report_path = EXAMPLE / ".sanka/acceptance.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    report = accept(args.revision)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "outcome": report["outcome"],
                "example": report["example"],
                "scenarios_compared": report["scenarios_compared"],
            }
        )
    )
