# SPDX-License-Identifier: Apache-2.0
"""Exercise an external extension using published SDK/CLI wheels and public CLI commands."""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
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


def check(work: Path, report: dict, wheel: Path, template: Path) -> dict:
    def stage(name: str) -> None:
        report["stage"] = name
        print(f"Extension acceptance: {name}", file=sys.stderr, flush=True)

    stage("candidate selection")
    if not wheel.is_file() or not template.is_file():
        raise ValueError("Supply an existing candidate wheel and extension manifest template")
    report["candidate"] = {"filename": wheel.name, "sha256": sha(wheel)}
    stage("published SDK download and candidate installation")
    uv = shutil.which("uv")
    openssl = shutil.which("openssl")
    if not uv or not openssl:
        raise RuntimeError("Install uv and OpenSSL before running this check (macOS/Linux).")
    # No project dependencies, auth config or installed Sanka state are inherited.
    env = {
        key: os.environ[key]
        for key in (
            "PATH",
            "TMPDIR",
            "LANG",
            "SYSTEMROOT",
            "DEVELOPER_DIR",
            "UV_PYTHON",
        )
        if key in os.environ
    }
    env.update(
        UV_NO_CONFIG="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "SANKA_HOME"):
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
    shutil.copyfile(wheel, wheels / wheel.name)
    all_wheels = sorted(wheels.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        license_names = [n for n in archive.namelist() if n.endswith("/licenses/LICENSE")]
        assert len(license_names) == 1, "Wheel must bundle Apache license"
        assert b"Apache License" in archive.read(license_names[0])
    report["wheel_hashes"] = {p.name: sha(p) for p in all_wheels}
    cli_env = work / "cli"
    dev_env = work / "destination"
    for target in (cli_env, dev_env):
        run(uv, "venv", "--python", "3.12", str(target), cwd=work, env=env)
    run(
        uv,
        "pip",
        "install",
        "--python",
        str(cli_env / "bin/python"),
        f"sanka-cli=={CLI_VERSION}",
        cwd=work,
        env=env,
    )
    probe = "import importlib.util; assert importlib.util.find_spec('sanka_extension_llm_to_jev') is None"
    run(str(cli_env / "bin/python"), "-I", "-c", probe, cwd=work, env=env)
    run(str(dev_env / "bin/python"), "-I", "-c", probe, cwd=work, env=env)
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
        manifest = json.loads(template.read_text())
        # Build the fixture for this explicit test pair before the old CLI installs it.
        # Never widen or repair the installed manifest/lock after upgrading.
        assert manifest["runtime"]["sanka_cli"] == f"=={CLI_VERSION}"
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
                    "extensions": [{"id": "sanka/llm-to-jev", "manifest": "extension.json"}],
                },
                indent=2,
            )
            + "\n"
        )
        project = work / "project"
        shutil.copytree(
            ROOT / "source",
            project,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
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
            "jev-candidate",
            code="SANKA_MARKETPLACE_TRUST_REQUIRED",
        )
        command(
            "extension",
            "marketplace",
            "add",
            str(catalog),
            "--name",
            "jev-candidate",
            "--trust",
        )
        command("extension", "add", "sanka/llm-to-jev", "--marketplace", "jev-candidate")
        originals = {
            p.relative_to(project).as_posix(): p.read_bytes()
            for p in project.rglob("*")
            if p.is_file() and ".sanka" not in p.parts
        }
        lock_path = project / ".sanka/extensions.lock"
        previous_lock = lock_path.read_bytes()
        stage("full public CLI lifecycle")
        command("scan", ".")
        command("plan", ".", "--to", "jev-classifier")
        core_plan = json.loads((project / ".sanka/plan.json").read_text())
        plan_hash = core_plan["plan_hash"]
        command("apply", "--root", ".", "--plan-hash", plan_hash)
        artifact_root = project / ".sanka/extensions/sanka/llm-to-jev"
        candidate = artifact_root / "candidate"
        assert candidate.is_dir()
        # Destination dependencies belong only to the destination environment.
        install_env = {key: value for key, value in env.items() if key != "SSL_CERT_FILE"}
        run(
            uv,
            "pip",
            "install",
            "--python",
            str(dev_env / "bin/python"),
            "-r",
            str(candidate / "requirements-jev.txt"),
            cwd=work,
            env=install_env,
        )
        if (candidate / "requirements.txt").is_file():
            run(
                uv,
                "pip",
                "install",
                "--python",
                str(dev_env / "bin/python"),
                "-r",
                str(candidate / "requirements.txt"),
                cwd=work,
                env=install_env,
            )
        report["installed_versions"] = json.loads(
            run(
                str(dev_env / "bin/python"),
                "-I",
                "-c",
                "import json; from importlib.metadata import distributions; "
                "print(json.dumps({d.metadata['Name']: d.version for d in distributions()}))",
                cwd=work,
                env=env,
            )
        )
        actual_cli = run(
            str(cli_env / "bin/python"),
            "-I",
            "-c",
            "from importlib.metadata import version; print(version('sanka-cli'))",
            cwd=work,
            env=env,
        ).strip()
        assert actual_cli == CLI_VERSION
        phase_config = json.dumps({"candidate_python": str(dev_env / "bin/python")})
        command("test", ".", "--extension-config", phase_config)
        command("verify", ".")
        for name in ("compatibility-report.json", "verification-report.json"):
            report[name] = json.loads((artifact_root / name).read_text())
        generated = {
            p.relative_to(candidate).as_posix(): sha(p)
            for p in candidate.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        command("apply", "--root", ".", "--plan-hash", plan_hash)
        assert generated == {
            p.relative_to(candidate).as_posix(): sha(p)
            for p in candidate.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        assert all((project / name).read_bytes() == value for name, value in originals.items())
        assert lock_path.read_bytes() == previous_lock
        report["source_hashes"] = {
            name: hashlib.sha256(value).hexdigest() for name, value in originals.items()
        }
        report["generated_hashes"] = generated
        report["core_plan_hash"] = plan_hash
        run(str(cli_env / "bin/python"), "-I", "-c", probe, cwd=work, env=env)
        installed = list((work / "sanka_home/extensions/environments").glob("*/bin/python"))
        assert len(installed) == 1
        run(
            str(installed[0]),
            "-B",
            "-I",
            "-c",
            "import importlib.util; import sanka_extension_llm_to_jev; "
            "assert importlib.util.find_spec('typesafe_sdk') is None; "
            "assert importlib.util.find_spec('openai') is None",
            cwd=work,
            env=env,
        )
        stage("tamper rejection")
        rejected(
            "apply",
            "--root",
            ".",
            "--plan-hash",
            "sha256:" + "0" * 64,
            code="SANKA_EXTENSION_PLAN_HASH_MISMATCH",
        )
        source_file = next(project.glob("*.py"))
        source_file.write_bytes(source_file.read_bytes() + b"\n# changed source\n")
        rejected(
            "apply",
            "--root",
            ".",
            "--plan-hash",
            plan_hash,
            code="lifecycle_rejected",
        )
        source_file.write_bytes(originals[source_file.name])
        plan_file = artifact_root / "migration-plan.json"
        plan_bytes = plan_file.read_bytes()
        plan_file.write_bytes(plan_bytes + b" ")
        rejected(
            "apply",
            "--root",
            ".",
            "--plan-hash",
            plan_hash,
            code="SANKA_EXTENSION_IDENTITY",
        )
        plan_file.write_bytes(plan_bytes)
        # Use fresh state so a good cached wheel cannot conceal a changed download.
        env["SANKA_HOME"] = str(work / "tamper-home")
        project = work / "tamper-project"
        shutil.copytree(
            ROOT / "source",
            project,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        wheel = next(w for w in all_wheels if w.name.startswith("sanka_extension_llm_to_jev"))
        wheel.write_bytes(wheel.read_bytes() + b"tampered")
        command(
            "extension",
            "marketplace",
            "add",
            str(catalog),
            "--name",
            "jev-candidate",
            "--trust",
        )
        rejected(
            "extension",
            "add",
            "sanka/llm-to-jev",
            "--marketplace",
            "jev-candidate",
            code="SANKA_EXTENSION_HASH_MISMATCH",
        )
        return {
            "status": "passed",
            "cli": CLI_VERSION,
            "sdk": "0.1.0a4",
            "mode": "mocks",
            "live_verified": False,
            "checks": [
                "bundled Apache license",
                "complete extension wheel hash closure",
                "explicit marketplace trust",
                "isolated CLI/extension/destination",
                "scan",
                "plan",
                "apply",
                "test",
                "verify",
                "deterministic reapply",
                "source preserved",
                "changed source rejected",
                "changed plan rejected",
                "incorrect reviewed hash rejected",
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
    parser.add_argument("--extension-wheel", required=True, type=Path)
    parser.add_argument("--extension-template", required=True, type=Path)
    args = parser.parse_args()
    report = {"status": "failed", "stage": "setup"}
    try:
        with tempfile.TemporaryDirectory(prefix="sanka-jev-check-") as directory:
            report.update(
                check(
                    Path(directory),
                    report,
                    args.extension_wheel.resolve(),
                    args.extension_template.resolve(),
                )
            )
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
