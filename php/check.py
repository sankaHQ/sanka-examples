# SPDX-License-Identifier: Apache-2.0
"""Exercise candidate PHP wheels through the installed public CLI on disposable Linux."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candidate import Candidate, sha  # noqa: E402

ENV_NAMES = (
    "SANKA_PHP_REPLAY", "SANKA_PHP_FRAMEWORK", "SANKA_PHP_PYTHON",
    "SANKA_PHP_GOMODCACHE", "SANKA_PHP_GOCACHE", "SANKA_PHP_MYSQL_ADMIN_URL",
    "SANKA_PHP_MYSQL_SOCKET",
)


class PhpCandidate(Candidate):
    def __init__(self, source: Path, extension: str, target: str, bundle: Path, revision: str):
        super().__init__(source, extension, [], [target], "sanka-php.json", revision, "0.3.9")
        self.bundle = bundle.resolve(strict=True)

    def _setup(self):
        self._prepare_workspace()
        manifest = json.loads((self.bundle / f"sanka-extension-{self.extension}.json").read_text())
        if manifest["id"] != "sanka/" + self.extension or manifest["version"] != "0.1.0a1":
            raise ValueError("Candidate identity differs from the requested PHP extension")
        wheels = self.root / "wheels"
        wheels.mkdir()
        for entry in manifest["wheels"]:
            name = entry["name"]
            if Path(name).name != name or not name.endswith(".whl"):
                raise ValueError("Invalid candidate wheel path")
            path = self.bundle / name
            if path.is_symlink() or sha(path) != entry["sha256"]:
                raise ValueError("Candidate wheel checksum mismatch")
            shutil.copyfile(path, wheels / name)
        self.report["wheels"] = {p.name: sha(p) for p in sorted(wheels.glob("*.whl"))}
        self.report["source_manifest_sha256"] = sha(self.bundle / f"sanka-extension-{self.extension}.json")
        self._install_cli()
        self._serve_candidate(wheels)
        self.env.update({key: os.environ[key] for key in ENV_NAMES if key in os.environ})


def hashes(source: Path) -> dict[str, str]:
    return {
        p.relative_to(source).as_posix(): sha(p)
        for p in sorted(source.rglob("*"))
        if p.is_file() and ".sanka" not in p.relative_to(source).parts
    }


def qualify(bundle: Path, revision: str, scan_only: bool):
    if not scan_only and (sys.platform != "linux" or os.environ.get("SANKA_PHP_REPLAY") != "1"):
        raise ValueError("Full acceptance requires an explicitly prepared disposable Linux environment")
    output = ROOT / "php/.sanka/evidence"
    output.mkdir(parents=True, exist_ok=True)
    for example in ("custom-json-api", "laravel-orders-api"):
        for extension, target in (("php-to-fastapi", "fastapi"), ("php-to-golang", "chi")):
            destination = output / f"{example}-{target}.json"
            destination.unlink(missing_ok=True)
            source = ROOT / "php" / example / "source"
            before = hashes(source)
            with PhpCandidate(source, extension, target, bundle, revision) as candidate:
                env_args = [part for name in ENV_NAMES if name in candidate.env for part in ("--extension-env", name)]
                stages = {}
                for stage in ("scan", "plan"):
                    args = [stage, str(candidate.project), *env_args]
                    if stage == "plan":
                        args += ["--to", target]
                    result = candidate.cli(*args)
                    stages[stage] = result["outcome"]
                if not scan_only:
                    plan_hash = str(result["data"]["plan_hash"])
                    applied = candidate.cli("apply", "--root", str(candidate.project), "--plan-hash", plan_hash, *env_args)
                    stages["apply"] = applied["outcome"]
                    for stage in ("test", "verify"):
                        stages[stage] = candidate.cli(stage, str(candidate.project), *env_args)["outcome"]
                if hashes(source) != before or hashes(candidate.project) != before:
                    raise ValueError("Acceptance changed the original PHP source")
                reports = list(candidate.project.glob(f".sanka/extensions/sanka/{extension}/verify.json"))
                report = json.loads(reports[0].read_text()) if len(reports) == 1 else None
                if not scan_only and (not report or report.get("ok") is not True):
                    raise ValueError("Successful CLI stages lack actual PHP parity evidence")
                generated = candidate.project / ".sanka/extensions/sanka" / extension / target
                receipt = {
                    "status": "scan_plan_only" if scan_only else "passed_within_scope",
                    "candidate": candidate.report,
                    "stages": stages,
                    "source_preserved": True,
                    "source_sha256": before,
                    "generated_sha256": hashes(generated) if generated.is_dir() else {},
                    "parity": report,
                    "complete_backend": False,
                }
                destination.write_text(json.dumps(receipt, indent=2) + "\n")
                print(example, target, receipt["status"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--scan-plan-only", action="store_true")
    args = parser.parse_args()
    qualify(args.bundle, args.revision, args.scan_plan_only)
