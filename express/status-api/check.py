"""Clean public-CLI consumer acceptance for the published Express-to-axum converter."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
# The published consumer keeps the ``Candidate`` name: the extensions release
# qualification substitutes this symbol with its own release-wheel consumer.
from candidate import PUBLISHED_REVISION, Published as Candidate
from source_check import available_port, wait_observe


def hashes(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()
            and not any(part in {".sanka", "node_modules", "__pycache__"} for part in p.relative_to(root).parts)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / ".sanka/acceptance.json")
    args = parser.parse_args()
    candidate = Candidate(ROOT, "typescript-to-rust", ["sanka-ts-capture", "sanka-http-replay"], ["axum"], "src/app.ts", revision=PUBLISHED_REVISION)
    report = {"status": "failed", "stages": {name: "not_run" for name in ("source", "scan", "plan", "apply", "test", "verify", "target_build", "http_comparison")}, "platform": platform.platform(), "unsupported": ["middleware", "dynamic payloads", "database and write handlers", "production cutover"]}
    try:
        with candidate as c:
            # Evidence describes a run, and is not part of the source application.
            (c.project / "evidence.json").unlink(missing_ok=True)
            before = hashes(c.project)
            c.run("npm", "ci", "--no-audit", "--no-fund")
            c.run("npm", "run", "build")
            report["source_http"] = json.loads(c.run(sys.executable, "source_check.py"))["source_http"]
            report["stages"]["source"] = "passed"
            c.env["SANKA_NODE"] = str(c.project / "node_modules/node/bin/node")
            c.env["SANKA_NODE_TOOLS"] = str(c.project / "node_modules")
            c.env["RUSTUP_HOME"] = os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
            c.env["CARGO_HOME"] = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
            c.env["CARGO_TARGET_DIR"] = str(c.root / "rust-target")
            c.env["CARGO_BUILD_JOBS"] = "2"
            c.env["PATH"] = str(c.project / "node_modules/.bin") + os.pathsep + c.env["PATH"]
            report["toolchains"] = {"node": c.run(c.env["SANKA_NODE"], "--version").strip(), "rust": c.run("rustc", "+1.93.1", "--version").strip()}
            config = json.dumps({"source_framework": "express", "target_framework": "axum", "source_file": "src/app.ts"})
            flags = ["--extension-config", config]
            for name in ("SANKA_NODE", "SANKA_NODE_TOOLS", "RUSTUP_HOME", "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_BUILD_JOBS", "DEVELOPER_DIR"):
                if name in c.env:
                    flags.extend(["--extension-env", name])
            c.cli("scan", ".", *flags)
            extension_root = c.project / ".sanka/extensions/sanka/typescript-to-rust"
            scan = json.loads((extension_root / "scan.json").read_text())
            assert scan["gaps"] == [], scan["gaps"]
            report["stages"]["scan"] = "passed"
            c.cli("plan", ".", "--to", "axum", *flags)
            plan = json.loads((extension_root / "plan.json").read_text())
            core = json.loads((c.project / ".sanka/plan.json").read_text())
            assert plan["capture"]["gaps"] == []
            assert len(plan["capture"]["routes"]) == 2
            assert plan["capture"]["launcher"] == "src/server.ts"
            assert set(plan["files"]) == {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "src/lib.rs", "src/main.rs", "contract.json", "README.md"}
            # Repeat planning before accepting the exact reviewed runtime plan hash.
            c.cli("plan", ".", "--to", "axum", *flags)
            assert json.loads((extension_root / "plan.json").read_text()) == plan
            assert json.loads((c.project / ".sanka/plan.json").read_text())["plan_hash"] == core["plan_hash"]
            report["stages"]["plan"] = "passed"
            report["extension_plan_hash"] = plan["plan_hash"]
            report["reviewed_runtime_plan_hash"] = core["plan_hash"]
            try:
                c.cli("apply", "--plan-hash", "sha256:" + "0" * 64, *flags)
            except RuntimeError as error:
                if "SANKA_EXTENSION_PLAN_HASH_MISMATCH" not in str(error):
                    raise
            else:
                raise AssertionError("apply accepted an unreviewed plan hash")
            assert not (extension_root / "rust").exists()
            report["unreviewed_plan_rejected"] = True
            c.cli("apply", "--plan-hash", core["plan_hash"], *flags)
            report["stages"]["apply"] = "passed"
            output = extension_root / "rust"
            generated = hashes(output)
            assert generated == {name: hashlib.sha256(text.encode()).hexdigest() for name, text in plan["files"].items()}
            report["generated_sha256"] = generated
            for stage in ("test", "verify"):
                c.cli(stage, *flags)
                result = json.loads((extension_root / f"{stage}.json").read_text())
                assert result["ok"] is True
                report[stage] = result
                report["stages"][stage] = "passed"
            c.run("cargo", "build", "--locked", cwd=output)
            report["stages"]["target_build"] = "passed"
            port = available_port()
            process = subprocess.Popen([str(c.root / "rust-target/debug/migrated-backend")], cwd=output, env=c.env | {"HOST": "127.0.0.1", "PORT": str(port)}, stdout=subprocess.DEVNULL)
            try:
                report["target_http"] = wait_observe(process, port)
            finally:
                process.terminate()
                process.wait(timeout=10)
            for path, source in report["source_http"].items():
                target = report["target_http"][path]
                assert (source["status"], source["body"], source["raw_body"]) == (target["status"], target["body"], target["raw_body"])
            report["stages"]["http_comparison"] = "passed"
            assert hashes(c.project) == before, "source files changed"
            report["source_sha256"] = before
            report["source_preserved"] = True
            report["status"] = "passed"
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        report["candidate"] = candidate.report
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": report["status"], "stages": report["stages"], "report": str(args.report)}))


if __name__ == "__main__":
    main()
