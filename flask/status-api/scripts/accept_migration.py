# SPDX-License-Identifier: Apache-2.0
"""Clean-consumer acceptance. Downloads pinned packages; uses only local HTTP."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1]
REPOSITORY = EXAMPLE.parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
from released import Released as Candidate  # noqa: E402

CONFIG = json.dumps({"source_framework": "flask", "target_framework": "fiber",
                     "source_file": "app.py", "database_layer": "none"})


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()
            and not {".sanka", "__pycache__", ".venv"}.intersection(p.relative_to(root).parts)}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def server(command, cwd, env, number):
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read().decode())
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{number}/health", timeout=1):
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Local server did not become ready within ten seconds")
        yield
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        process.stderr.close()


def http(number, case):
    with urllib.request.urlopen(f"http://127.0.0.1:{number}{case['path']}", timeout=5) as response:
        return {"method": "GET", "path": case["path"], "status": response.status,
                "media_type": response.headers.get_content_type(),
                "body": json.loads(response.read())}


def accept():
    original = hashes(EXAMPLE / "source")
    expected = json.loads((EXAMPLE / "expected.json").read_text())
    dependencies = (EXAMPLE / "source/requirements.txt").read_text().splitlines()
    with Candidate(example=EXAMPLE / "source", extension="python-to-golang", packages=[],
                   targets=["fiber"], match_file="app.py") as candidate:
        project = candidate.project
        source_env = candidate.root / "source-env"
        candidate.run("uv", "venv", "--python", "3.12", str(source_env))
        python = str(source_env / "bin/python")
        candidate.run("uv", "pip", "install", "--python", python, *dependencies)
        candidate.env["SANKA_GO_SOURCE_PYTHON"] = python
        candidate.report["source_dependencies"] = dependencies
        candidate.report["source_python"] = candidate.run(python, "--version").strip()
        candidate.env.update(GOMAXPROCS="2", GOFLAGS="-p=2")

        def cli(*args):
            return candidate.cli(*args, "--extension-env", "SANKA_GO_SOURCE_PYTHON",
                                 "--extension-env", "GOMAXPROCS", "--extension-env", "GOFLAGS")

        before = hashes(project)
        stages = {}
        for stage in ("scan", "plan"):
            args = [stage, ".", "--extension-config", CONFIG]
            if stage == "plan":
                args.extend(["--to", "fiber"])
            stages[stage] = cli(*args)
        plan = stages["plan"]["data"]
        require(not plan["capture"]["gaps"], f"Unexpected capture gaps: {plan['capture']['gaps']}")
        require(plan["capture"]["routes"] == [
            {key: value for key, value in case.items() if key != "media_type"} for case in expected
        ], "Reviewed routes differ from the explicit source behavior")
        repeated = cli("plan", ".", "--to", "fiber", "--extension-config", CONFIG)
        require(repeated["data"]["plan_hash"] == plan["plan_hash"], "Plan is not reproducible")
        require(set(plan["files"]) >= {"go.mod", "go.sum", "cmd/api/main.go"},
                "Reviewed plan does not contain the expected runnable target")
        wrong_hash_rejected = False
        try:
            cli("apply", "--plan-hash", "sha256:" + "0" * 64)
        except RuntimeError as error:
            wrong_hash_rejected = "SANKA_EXTENSION_PLAN_HASH_MISMATCH" in str(error)
        require(wrong_hash_rejected, "Apply accepted an unreviewed plan hash")
        output = project / ".sanka/extensions/sanka/python-to-golang/golang"
        require(not output.exists(), "Rejected apply created destination files")
        stages["apply"] = cli("apply", "--plan-hash", plan["plan_hash"])
        generated = hashes(output)
        expected_hashes = {name: hashlib.sha256(content.encode()).hexdigest()
                           for name, content in plan["files"].items()}
        require(generated == expected_hashes, "Generated files differ from the reviewed plan")
        stages["test"] = cli("test")
        require(stages["test"]["data"]["ok"] is True, "test did not explicitly pass")
        # Preserve independent build/HTTP evidence if public verification fails;
        # such a run remains blocked and exits nonzero.
        try:
            stages["verify"] = cli("verify")
            require(stages["verify"]["data"]["ok"] is True, "verify did not explicitly pass")
        except RuntimeError as error:
            stages["verify"] = {"outcome": "error", "error": str(error)}

        # Reuse the candidate's qualified compiler if lifecycle bootstrapped it.
        compilers = sorted((project / ".sanka/go-toolchain").glob("**/bin/go"))
        go = str(compilers[0]) if compilers else shutil.which("go", path=candidate.env["PATH"])
        require(go is not None, "Qualified Go compiler missing")
        env = dict(candidate.env, GOTOOLCHAIN="local", GOCACHE=str(candidate.root / "go-cache"),
                   GOMODCACHE=str(candidate.root / "go-modules"), CGO_ENABLED="0",
                   GOMAXPROCS="2", GOFLAGS="-p=2")

        def run(*args):
            return subprocess.check_output(args, cwd=output, env=env, text=True,
                                           stderr=subprocess.STDOUT, timeout=300).strip()

        version = run(go, "version")
        require("go1.26.5 " in version, f"Unqualified compiler: {version}")
        native_checks = {"test": run(go, "test", "./..."), "vet": run(go, "vet", "./...")}
        binary = candidate.root / "status-api"
        native_checks["build"] = run(go, "build", "-o", str(binary), "./cmd/api")
        source_port, target_port = port(), port()
        while source_port == target_port:
            target_port = port()
        responses = []
        with server([python, "-m", "flask", "--app", "app", "run", "--host", "127.0.0.1",
                     "--port", str(source_port), "--no-reload"], project, candidate.env, source_port):
            with server([str(binary)], output, dict(env, PORT=str(target_port)), target_port):
                for case in expected:
                    source, target = http(source_port, case), http(target_port, case)
                    require(source == target == case, f"HTTP mismatch: {source!r}; {target!r}")
                    responses.append({"source": source, "target": target, "equal": True})
        require(hashes(project) == before, "Migration changed the copied source")
        require(hashes(EXAMPLE / "source") == original, "Migration changed the original source")
        require(hashes(output) == generated, "Acceptance changed generated files")
        artifacts = EXAMPLE / ".sanka"
        artifacts.mkdir(exist_ok=True)
        retained = Path(tempfile.mkdtemp(prefix="accepted-", dir=artifacts))
        shutil.copytree(output, retained / "golang")
        (retained / "stages.json").write_text(json.dumps(stages, indent=2) + "\n")
        return {"schema": "sanka-examples/acceptance/v1", "example": "flask/status-api",
                "outcome": "passed" if stages["verify"]["outcome"] == "success" else "blocked",
                "retained_artifacts": str(retained),
                "verification_error": stages["verify"].get("error"),
                "candidate": candidate.report, "source_sha256": original,
                "extension_plan_hash": plan["extension"]["plan_hash"],
                "reviewed_core_plan_hash": plan["plan_hash"],
                "generated_sha256": generated, "source_preserved": True,
                "repeated_plan_identical": True, "wrong_plan_rejected": True,
                "stages": {name: result["outcome"] for name, result in stages.items()},
                "go_toolchain": version, "native_checks": native_checks,
                "http_comparison": responses, "unsupported": [
                    "Database and write handlers", "Other Go routers", "Authentication and middleware",
                    "HEAD/OPTIONS, default errors, redirects and content negotiation", "Whole-app parity"],
                "not_run": ["Production deployment", "Database migrations"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=EXAMPLE / ".sanka/acceptance.json")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # Invalidate previous evidence before starting a potentially failing rerun.
    args.report.unlink(missing_ok=True)
    try:
        report = accept()
    except Exception as error:
        args.report.write_text(json.dumps({"example": "flask/status-api", "outcome": "failed",
                                          "error": str(error)}, indent=2) + "\n")
        raise
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["outcome"] != "passed":
        sys.exit(1)
