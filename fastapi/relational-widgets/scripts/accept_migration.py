# SPDX-License-Identifier: Apache-2.0
"""Exercise the published Python-to-Go wheel against disposable PostgreSQL schemas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql

EXAMPLE = Path(__file__).resolve().parents[1]
REPOSITORY = EXAMPLE.parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
from candidate import Published

RELEASE_TAG = "api-converters-v0.1.0a7"
RELEASE_REVISION = "0dee899b2da67a1f2e801fffc5234c5219818887"
CONFIG = {
    "source_framework": "fastapi",
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


def database_state(dsn: str) -> dict:
    with psycopg.connect(dsn) as connection:
        return {
            "parents": connection.execute(
                "SELECT * FROM parents ORDER BY id"
            ).fetchall(),
            "widgets": connection.execute(
                "SELECT * FROM widgets ORDER BY id"
            ).fetchall(),
            "indexes": connection.execute(
                "SELECT tablename,indexname FROM pg_indexes "
                "WHERE schemaname=current_schema() AND tablename IN ('parents','widgets') "
                "ORDER BY tablename,indexname"
            ).fetchall(),
            "sequences": connection.execute(
                "SELECT sequencename,last_value FROM pg_sequences "
                "WHERE schemaname=current_schema() "
                "AND sequencename IN ('parents_id_seq','widgets_id_seq') "
                "ORDER BY sequencename"
            ).fetchall(),
        }


CASES = [
    {"method": "PATCH", "path": "/parents/4", "body": {"note": "transferred"}},
    {
        "method": "PATCH",
        "path": "/widgets/23",
        "body": {"enabled": False, "note": None},
    },
    {
        "method": "POST",
        "path": "/parents",
        "body": {"name": "fresh", "count": 0, "enabled": False},
    },
    {
        "method": "POST",
        "path": "/widgets",
        "body": {"name": "new-child", "parent_id": 4, "enabled": True},
    },
    {
        "method": "POST",
        "path": "/widgets",
        "body": {"name": "invalid-child", "parent_id": 999, "enabled": True},
    },
    {"method": "DELETE", "path": "/parents/4"},
    {"method": "DELETE", "path": "/widgets/15"},
]


def go_response(address: str, case: dict) -> dict:
    body = json.dumps(case["body"]).encode() if "body" in case else None
    request = Request(
        address + case["path"],
        data=body,
        method=case["method"],
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        content = response.read()
        return {
            "status": response.status,
            "media_type": response.headers.get("Content-Type", "").split(";")[0],
            "body": json.loads(content) if content else None,
        }


def transfer_existing(
    consumer: Published,
    project: Path,
    output: Path,
    python: str,
    go: str,
    source_url: str,
    target_url: str,
) -> dict:
    consumer.run(
        python,
        str(EXAMPLE / "scripts/seed_source.py"),
        str(project),
        env=consumer.env | {"DATABASE_URL": source_url},
    )
    before = database_state(source_url)
    runtime_env = consumer.env | {
        "DATABASE_URL": target_url,
        "GOTOOLCHAIN": "local",
        "GOWORK": "off",
    }
    migrate = consumer.root / "migrate-transfer"
    consumer.run(
        go,
        "build",
        "-mod=readonly",
        "-o",
        str(migrate),
        "./cmd/migrate",
        cwd=output,
        env=runtime_env,
    )
    consumer.run(str(migrate), "up", cwd=output, env=runtime_env)
    transfer_env = consumer.env | {
        "SANKA_GO_SOURCE_DATABASE_URL": source_url,
        "DATABASE_URL": target_url,
    }

    def transfer(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(output / "tools/transfer_existing.py"), *args],
            env=transfer_env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    dry = transfer()
    require(dry.returncode == 0, "Transfer dry run failed")
    dry_report = json.loads(dry.stdout)
    require(
        dry_report
        == {
            "mode": "dry-run",
            "rows": {"parents": 2, "widgets": 3},
            "excluded_tables": ["alembic_version"],
        },
        "Transfer dry run did not inventory source rows and exclusions",
    )
    unacknowledged = transfer("--execute")
    require(
        unacknowledged.returncode != 0
        and "acknowledge-excluded-tables" in unacknowledged.stderr,
        "Transfer failed to require excluded-table acknowledgement",
    )
    copied = transfer("--execute", "--acknowledge-excluded-tables")
    require(copied.returncode == 0, "Existing-row transfer failed")
    verified = transfer("--verify")
    require(verified.returncode == 0, "Existing-row verification failed")
    require(
        json.loads(verified.stdout)["rows"] == dry_report["rows"],
        "Verified row count changed",
    )
    after = database_state(target_url)
    require(
        after == before,
        "Transferred state differs: "
        + str(
            {
                key: (before[key], after[key])
                for key in before
                if before[key] != after[key]
            }
        ),
    )
    again = transfer("--execute", "--acknowledge-excluded-tables")
    require(
        again.returncode != 0 and "nonempty" in again.stderr,
        "Transfer accepted a nonempty target",
    )

    cases = consumer.root / "transfer-cases.json"
    cases.write_text(json.dumps(CASES))
    source_results = json.loads(
        consumer.run(
            python,
            str(EXAMPLE / "scripts/source_probe.py"),
            str(project),
            str(cases),
            env=consumer.env
            | {
                "DATABASE_URL": source_url.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
            },
        )
    )
    app_binary = consumer.root / "api-transfer"
    consumer.run(
        go,
        "build",
        "-mod=readonly",
        "-o",
        str(app_binary),
        "./cmd/api",
        cwd=output,
        env=runtime_env,
    )
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    process = subprocess.Popen(
        [str(app_binary)],
        cwd=output,
        env=runtime_env | {"PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    address = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urlopen(address + "/__ready__", timeout=1):
                    pass
                break
            except HTTPError:
                break
            except URLError:
                require(
                    process.poll() is None,
                    "Generated Go server exited before HTTP replay",
                )
                require(
                    time.monotonic() < deadline, "Generated Go server did not start"
                )
                time.sleep(0.1)
        target_results = [go_response(address, case) for case in CASES]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    require(
        source_results == target_results,
        "Source and Go HTTP behavior differ after row transfer",
    )
    require(
        database_state(target_url) == database_state(source_url),
        "Post-HTTP PostgreSQL state differs",
    )
    consumer.run(str(migrate), "down", cwd=output, env=runtime_env)
    with psycopg.connect(target_url) as target:
        remaining = target.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema=current_schema() "
            "AND table_name IN ('parents','widgets')"
        ).fetchone()[0]
    require(remaining == 0, "Transfer target rollback left application tables")
    return {
        "dry_run": dry_report,
        "rows_verified": True,
        "indexes_verified": True,
        "sequences_verified": True,
        "repeat_copy_rejected": True,
        "http_comparison": [
            {"case": case, "source": source, "target": target}
            for case, source, target in zip(
                CASES, source_results, target_results, strict=True
            )
        ],
        "rollback_tables_removed": True,
    }


def accept(revision: str, target: str) -> dict:
    require(
        len(revision) == 40 and all(c in "0123456789abcdef" for c in revision),
        "Pin the published a7 merge commit before running acceptance",
    )
    dsn = os.environ["SANKA_MIGRATE_TEST_POSTGRES_DSN"]
    original = hashes(EXAMPLE / "source")
    with Published(
        example=EXAMPLE / "source",
        extension="python-to-golang",
        packages=[],
        targets=[target],
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
        schemas = ["example_" + uuid.uuid4().hex for _ in range(4)]
        with psycopg.connect(dsn, autocommit=True) as admin:
            try:
                for schema in schemas:
                    admin.execute(
                        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
                    )
                source_url, target_url, transfer_source_url, transfer_target_url = [
                    schema_url(dsn, schema) for schema in schemas
                ]
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

                config = json.dumps(CONFIG | {"target_framework": target})
                scan = cli("scan", ".", "--extension-config", config)
                require(scan["outcome"] == "success", "Scan failed")
                plan = cli("plan", ".", "--to", target, "--extension-config", config)[
                    "data"
                ]
                require(
                    plan["capture"]["generation_ready"] and not plan["capture"]["gaps"],
                    "The source has unsupported conversion gaps",
                )
                require(
                    plan["plan_hash"]
                    == cli("plan", ".", "--to", target, "--extension-config", config)[
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
                    for schema in schemas[:2]
                ]
                require(indexes[0] == indexes[1], "Source and Go indexes differ")
                compilers = sorted((project / ".sanka/go-toolchain").glob("**/bin/go"))
                go = (
                    str(compilers[0])
                    if compilers
                    else shutil.which("go", path=consumer.env["PATH"])
                )
                require(go is not None, "Qualified Go compiler missing")
                transfer = transfer_existing(
                    consumer,
                    project,
                    output,
                    python,
                    go,
                    transfer_source_url,
                    transfer_target_url,
                )
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
                    "target": target,
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
                    "transfer": transfer,
                    "unsupported": [
                        "Alembic branches and schema alterations",
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
    parser.add_argument(
        "--target", choices=["fiber", "chi", "mux", "gin"], default="fiber"
    )
    args = parser.parse_args()
    report_path = EXAMPLE / f".sanka/acceptance-{args.target}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    report = accept(args.revision, args.target)
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
