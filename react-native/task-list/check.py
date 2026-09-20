#!/usr/bin/env python3
"""Clean consumer acceptance. SwiftUI requires macOS and Swift; both paths need Node 22."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys

EXAMPLE = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE.parents[1] / "scripts"))
# The published consumer keeps the ``Candidate`` name: the extensions release
# qualification substitutes this symbol with its own release-wheel consumer.
from candidate import Published as Candidate

# Published catalog commit of the scoped mobile-converters-v0.1.0a1 prerelease.
RELEASE_REVISION = "826005294a616ae52bd166ee534a5b66513328b3"


def snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and not any(part in {".sanka", ".expo", "node_modules", "__pycache__"}
                    for part in p.relative_to(root).parts)
    }


def summarize(result: dict) -> dict:
    return {key: result.get(key, result.get("data", {}).get(key))
            for key in ["outcome", "migration_state", "plan_hash", "readiness", "gaps"]}


def accept(target: str, report: dict) -> None:
    if target == "swiftui" and platform.system() != "Darwin":
        raise RuntimeError("SwiftUI requires macOS; a platform skip is not acceptance")
    with Candidate(EXAMPLE, "react-native-to-native", ["sanka-ts-capture"],
                   ["swiftui", "compose"], "App.tsx", revision=RELEASE_REVISION) as c:
        report.update(c.report)
        # A checked-in evidence summary must not become part of its own source hash.
        (c.project / "evidence.json").unlink(missing_ok=True)
        c.env.update(EXPO_NO_TELEMETRY="1", CI="1")
        node = shutil.which("node", path=c.env["PATH"])
        if not node or not c.run(node, "--version").startswith("v22."):
            raise RuntimeError("Node.js 22 must be on PATH")
        c.env["SANKA_NODE"] = node
        report["source_checks"] = {}
        for command in [("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
                        ("npm", "run", "check"), ("npm", "run", "bundle")]:
            c.run(*command)
            report["source_checks"][" ".join(command)] = "passed"
        c.env["SANKA_NODE_TOOLS"] = str(c.project / "node_modules")
        before = snapshot(c.project)
        artifact = f".sanka/{target}"
        config = json.dumps({"target_framework": target})
        common = ["--artifact-dir", artifact, "--extension-config", config]
        for key in ["SANKA_NODE", "SANKA_NODE_TOOLS", "DEVELOPER_DIR"]:
            if key in c.env:
                common += ["--extension-env", key]
        scan = c.cli("scan", ".", *common)
        assert scan["outcome"] == "success", scan
        report["stages"]["scan"] = summarize(scan)
        plan = c.cli("plan", ".", "--to", target, *common)
        assert plan["outcome"] == "success", plan
        report["stages"]["plan"] = summarize(plan)
        repeated = c.cli("plan", ".", "--to", target, *common)
        assert repeated["data"]["plan_hash"] == plan["data"]["plan_hash"], "Plan drift"
        report["repeated_plan_identical"] = True
        core_plan = json.loads((c.project / artifact / "plan.json").read_text())
        native_plan = core_plan["extension_plan"]
        assert native_plan["gaps"] == [], native_plan["gaps"]
        assert native_plan["capture"]["gaps"] == [], native_plan["capture"]["gaps"]
        assert native_plan["readiness"] == 1.0, native_plan["dispositions"]
        assert len(native_plan["capture"]["screens"]) == 2
        assert native_plan["generated"] is (target == "swiftui")
        report["extension_plan_hash"] = native_plan["plan_hash"]
        report["source_capture_digest"] = native_plan["capture"]["source_digest"]
        report["source_sha256"] = before
        extension_artifacts = c.project / artifact / "extensions/sanka/react-native-to-native"
        if target == "swiftui":
            reviewed = plan["data"]["plan_hash"]
            try:
                c.cli("apply", "--root", ".", "--to", target,
                      "--plan-hash", "sha256:" + "0" * 64, *common)
            except RuntimeError as error:
                assert "PLAN_HASH_MISMATCH" in str(error), str(error)
                report["unreviewed_plan_rejected"] = True
            else:
                raise AssertionError("Unreviewed plan was accepted")
            for stage in ["apply", "test", "verify"]:
                command = [stage, "--root", ".", "--to", target]
                if stage == "apply":
                    command += ["--plan-hash", reviewed]
                result = c.cli(*command, *common)
                assert result["outcome"] == "success", result
                report["stages"][stage] = summarize(result)
            generated = extension_artifacts / "native-swiftui"
            expected = {name: hashlib.sha256(text.encode()).hexdigest()
                        for name, text in native_plan["files"].items()}
            assert snapshot(generated) == expected, "Generated output differs from plan"
            report["generated_sha256"] = expected
            replay = json.loads((extension_artifacts / "verify.json").read_text())
            assert replay["ok"] is True and replay["complete_app"] is False, replay
            report["replay"] = {key: replay.get(key) for key in ["ok", "complete_app", "swift_version", "node_version", "react_version", "scope", "failures"]}
            scenarios = {(item["screen"], item["scenario"]) for item in replay["candidate"]}
            expected_scenarios = {("HomeScreen", "initial"), ("HomeScreen", "press:2"),
                                  ("HomeScreen", "type:1"), ("DetailScreen", "initial"),
                                  ("DetailScreen", "toggle:2")}
            assert scenarios == expected_scenarios, scenarios
            report["replay"]["scenarios"] = [list(item) for item in sorted(scenarios)]
        else:
            report["unsupported"] = ["apply", "test", "verify", "kotlin-generation", "android-build"]
        assert snapshot(c.project) == before, "Source changed during migration"
        report["source_preserved"] = True
        destination = EXAMPLE / ".sanka" / f"acceptance-{target}" / "artifacts"
        # Replace only this task's ignored acceptance artifacts; no stale files survive.
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(c.project / artifact, destination,
                        ignore=shutil.ignore_patterns("native-swiftui-build", ".build"))
        report["artifact_sha256"] = snapshot(destination)
        report["status"] = "passed_within_scope"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["swiftui", "compose"], default="swiftui")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    path = args.report or EXAMPLE / ".sanka" / f"acceptance-{args.target}" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running", "target": args.target, "complete_app": False,
        "stages": {name: {"outcome": "not_run"} for name in ["scan", "plan", "apply", "test", "verify"]},
        "source_app_execution": "not-run; see source_checks for Metro bundle result, no simulator/device session",
        "target_ios_execution": "not-run; macOS package build and structural replay only",
    }
    path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        accept(args.target, report)
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Acceptance evidence: {path}")


if __name__ == "__main__":
    main()
