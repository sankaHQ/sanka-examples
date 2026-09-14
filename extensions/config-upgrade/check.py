# SPDX-License-Identifier: Apache-2.0
"""Exercise an external extension using published SDK/CLI wheels and public CLI commands."""

from __future__ import annotations

import argparse
import email
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI_VERSION = "0.2.12"
SDK_RELEASE = "https://github.com/sankaHQ/extensions/releases/download/sdk-v0.1.0a4"
SDK_WHEELS = {
    "sanka_connector_sdk-0.1.0a12-py3-none-any.whl": "34da5c35aaa60fc19258e76b72a3eca58bf52fff96e2ccf9a0aa1115f8878d8e",
    "sanka_extension_sdk-0.1.0a4-py3-none-any.whl": "f1a6655095ab81e549137e1d9604492bda2a31677d674c6359b0a39a2da96307",
}


def run(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"{args} failed ({result.returncode})\n{result.stdout}\n{result.stderr}")
    return result.stdout


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def wheel_identity(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("Candidate wheel must have exactly one distribution METADATA")
        metadata = email.message_from_bytes(archive.read(names[0]))
    if metadata["Name"] != "sanka-cli":
        raise ValueError("Candidate wheel must contain sanka-cli")
    version = metadata["Version"] or ""
    version_tuple(version)
    return {"version": version, "sha256": sha(path), "filename": path.name}


def version_tuple(version: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("This release check requires a stable MAJOR.MINOR.PATCH CLI version")
    return tuple(map(int, version.split(".")))


def verify_lock(path: Path, original: bytes) -> str:
    if path.read_bytes() != original:
        raise AssertionError("CLI upgrade or execution changed the existing extension lock")
    return hashlib.sha256(original).hexdigest()


def check(work: Path, report: dict, candidate: Path | None, baseline: str) -> dict:
    def stage(name: str) -> None:
        report["stage"] = name
        print(f"Extension acceptance: {name}", file=sys.stderr, flush=True)

    stage("candidate selection")
    identity = wheel_identity(candidate) if candidate else {"version": CLI_VERSION}
    version = identity["version"]
    if version_tuple(version) < version_tuple(baseline):
        raise ValueError("Candidate must not be older than the upgrade baseline")
    report.update(candidate=identity, upgrade_from=baseline)
    stage("published SDK download and example build")
    uv = shutil.which("uv")
    openssl = shutil.which("openssl")
    if not uv or not openssl:
        raise RuntimeError("Install uv and OpenSSL before running this check (macOS/Linux).")
    # No project dependencies, auth config or installed Sanka state are inherited.
    env = {
        key: os.environ[key]
        for key in ("PATH", "TMPDIR", "LANG", "SYSTEMROOT")
        if key in os.environ
    }
    env.update(
        UV_NO_CONFIG="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "SANKA_HOME"):
        target = work / name.lower()
        target.mkdir()
        env[name] = str(target)
    wheels = work / "wheels"
    wheels.mkdir()
    for filename, digest in SDK_WHEELS.items():
        with urllib.request.urlopen(f"{SDK_RELEASE}/{filename}", timeout=60) as response:
            (wheels / filename).write_bytes(response.read())
        if sha(wheels / filename) != digest:
            raise RuntimeError(f"Published SDK hash mismatch: {filename}")
    run(uv, "build", "--wheel", "--out-dir", str(wheels), str(ROOT), cwd=work, env=env)
    all_wheels = sorted(wheels.glob("*.whl"))
    example_wheel = next(w for w in all_wheels if w.name.startswith("example_"))
    with zipfile.ZipFile(example_wheel) as archive:
        license_name = next(
            name for name in archive.namelist() if name.endswith("/licenses/LICENSE")
        )
        assert archive.read(license_name) == (ROOT / "LICENSE").read_bytes()
    cli_env = work / "cli"
    dev_env = work / "developer"
    for target in (cli_env, dev_env):
        run(uv, "venv", "--python", "3.12", str(target), cwd=work, env=env)
    run(
        uv,
        "pip",
        "install",
        "--python",
        str(cli_env / "bin/python"),
        f"sanka-cli=={baseline}",
        cwd=work,
        env=env,
    )
    run(
        uv,
        "pip",
        "install",
        "--python",
        str(dev_env / "bin/python"),
        "--no-index",
        "--no-deps",
        *(str(w) for w in all_wheels),
        cwd=work,
        env=env,
    )
    run(
        str(dev_env / "bin/python"),
        "-m",
        "unittest",
        "discover",
        "-s",
        str(ROOT / "tests"),
        cwd=work,
        env=env,
    )
    probe = (
        "import importlib.util; assert importlib.util.find_spec('example_config_upgrade') is None"
    )
    run(str(cli_env / "bin/python"), "-c", probe, cwd=work, env=env)
    cert = work / "localhost.pem"
    key = work / "localhost.key"
    config = work / "openssl.cnf"
    config.write_text(
        "[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
        "[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\n"
        "basicConstraints=critical,CA:TRUE\n"
    )
    run(
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-config",
        str(config),
        "-keyout",
        str(key),
        "-out",
        str(cert),
        cwd=work,
        env=env,
    )
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(wheels))
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Trust this one ephemeral localhost certificate only in the child CLI.
        # Wheel hashing, metadata checks and isolated installation remain enabled.
        env["SSL_CERT_FILE"] = str(cert)
        manifest = json.loads((ROOT / "extension.template.json").read_text())
        # Build the fixture for this explicit test pair before the old CLI installs it.
        # Never widen or repair the installed manifest/lock after upgrading.
        manifest["runtime"]["sanka_cli"] = f">={baseline},<={version}"
        report["fixture_runtime"] = manifest["runtime"]["sanka_cli"]
        manifest["wheels"] = [
            {
                "name": w.name,
                "sha256": sha(w),
                "url": f"https://localhost:{server.server_port}/{w.name}",
            }
            for w in all_wheels
        ]
        catalog = work / "marketplace"
        catalog.mkdir()
        (catalog / "extension.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (catalog / "marketplace.json").write_text(
            json.dumps(
                {
                    "schema_version": "sanka-marketplace/v1",
                    "extensions": [{"id": "example/config-upgrade", "manifest": "extension.json"}],
                },
                indent=2,
            )
            + "\n"
        )
        project = work / "project"
        shutil.copytree(ROOT / "fixture", project)
        cli = str(cli_env / "bin/sanka")

        def command(*args: str) -> dict:
            return json.loads(run(cli, *args, "--json", cwd=project, env=env))

        def rejected(*args: str, code: str) -> None:
            result = subprocess.run(
                [cli, *args, "--json"],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            payload = json.loads(result.stdout)
            if result.returncode == 0 or payload.get("error", {}).get("code") != code:
                raise AssertionError(f"Expected {code}: {result.stdout}\n{result.stderr}")

        stage("baseline installation and execution")
        rejected(
            "extension",
            "marketplace",
            "add",
            str(catalog),
            "--name",
            "starter",
            code="SANKA_MARKETPLACE_TRUST_REQUIRED",
        )
        command("extension", "marketplace", "add", str(catalog), "--name", "starter", "--trust")
        command("extension", "add", "example/config-upgrade", "--marketplace", "starter")
        original = (project / "example-app.json").read_bytes()
        lock_path = project / ".sanka/extensions.lock"
        previous_lock = lock_path.read_bytes()

        def scan_and_plan() -> dict:
            command("scan", ".")
            scan = json.loads((project / ".sanka/scan.json").read_text())
            assert scan["extension"]["source_sha256"] == hashlib.sha256(original).hexdigest()
            command("plan", ".", "--to", "example-config-v2")
            plan = json.loads(
                (project / ".sanka/extensions/example/config-upgrade/config-plan.json").read_text()
            )
            assert plan["proposed"] == {"schema_version": 2, "name": "Order tracker"}
            assert (project / "example-app.json").read_bytes() == original
            verify_lock(lock_path, previous_lock)
            return plan

        previous_plan = scan_and_plan()
        stage("candidate CLI upgrade")
        # Public network installation uses normal CA trust; localhost trust is only for CLI calls.
        install_env = {key: value for key, value in env.items() if key != "SSL_CERT_FILE"}
        requirement = str(candidate) if candidate else f"sanka-cli=={version}"
        run(
            uv,
            "pip",
            "install",
            "--python",
            str(cli_env / "bin/python"),
            "--reinstall-package",
            "sanka-cli",
            requirement,
            cwd=work,
            env=install_env,
        )
        actual = run(
            str(cli_env / "bin/python"),
            "-I",
            "-c",
            "from importlib.metadata import version; print(version('sanka-cli'))",
            cwd=work,
            env=env,
        ).strip()
        if actual != version:
            raise AssertionError(f"Installed CLI {actual} differs from candidate {version}")
        if candidate and sha(candidate) != identity["sha256"]:
            raise AssertionError("Candidate wheel bytes changed during installation")
        report["installed_cli"] = actual
        report["lock_sha256_before"] = verify_lock(lock_path, previous_lock)
        stage("candidate scan and plan with existing lock")
        plan = scan_and_plan()
        assert plan == previous_plan, "Candidate changed the extension's plan contents"
        report["lock_sha256_after"] = verify_lock(lock_path, previous_lock)
        run(str(cli_env / "bin/python"), "-c", probe, cwd=work, env=env)
        installed = list((work / "sanka_home/extensions/environments").glob("*/bin/python"))
        assert len(installed) == 1
        run(
            str(installed[0]),
            "-B",
            "-c",
            "import example_config_upgrade; assert example_config_upgrade.VERSION == '0.1.0'",
            cwd=work,
            env=env,
        )
        stage("candidate rejection checks")
        (project / "example-app.json").write_text('{"schema_version": 99}')
        rejected("scan", ".", code="EXAMPLE_INVALID_INPUT")
        (project / "example-app.json").write_bytes(original)
        # Use fresh state so a good cached wheel cannot conceal a changed download.
        env["SANKA_HOME"] = str(work / "tamper-home")
        project = work / "tamper-project"
        shutil.copytree(ROOT / "fixture", project)
        wheel = next(w for w in all_wheels if w.name.startswith("example_"))
        wheel.write_bytes(wheel.read_bytes() + b"tampered")
        command("extension", "marketplace", "add", str(catalog), "--name", "starter", "--trust")
        rejected(
            "extension",
            "add",
            "example/config-upgrade",
            "--marketplace",
            "starter",
            code="SANKA_EXTENSION_HASH_MISMATCH",
        )
        return {
            "status": "passed",
            "cli": version,
            "sdk": "0.1.0a4",
            "wheel_hashes": {item["name"]: item["sha256"] for item in manifest["wheels"]},
            "plan": plan,
            "checks": [
                "bundled Apache license",
                "installed-wheel unit tests",
                "explicit marketplace trust",
                "isolated wheel installation",
                "candidate CLI installed",
                "existing lock preserved before and after execution",
                "CLI scan",
                "CLI plan",
                "source unchanged",
                "invalid input rejected",
                "tampered wheel rejected",
            ],
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        key.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write acceptance evidence even on failure")
    parser.add_argument("--cli-wheel", type=Path, help="Candidate sanka-cli wheel to test")
    parser.add_argument(
        "--upgrade-from", default=CLI_VERSION, help="Published baseline CLI version"
    )
    args = parser.parse_args()
    report = {"status": "failed", "stage": "setup"}
    try:
        candidate = args.cli_wheel.resolve() if args.cli_wheel else None
        with tempfile.TemporaryDirectory(prefix="sanka-extension-starter-") as directory:
            report.update(check(Path(directory), report, candidate, args.upgrade_from))
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
