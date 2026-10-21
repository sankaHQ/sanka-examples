# SPDX-License-Identifier: Apache-2.0
"""Acceptance must reject non-success stages and misattributed candidate bytes."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from php.check import PhpCandidate


class RecordedCliCandidate(PhpCandidate):
    """Supply recorded CLI protocol output without installing or running a migration."""

    def run(self, *args, **kwargs):
        return json.dumps(self.response)


class PhpCandidateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.revision = "a" * 40
        self.wheel = self.root / "candidate.whl"
        self.wheel.write_bytes(b"candidate artifact")
        self.manifest = self.root / "sanka-extension-php-to-fastapi.json"
        self.manifest.write_text(json.dumps({
            "id": "sanka/php-to-fastapi", "version": "0.1.0a1",
            "wheels": [{"name": self.wheel.name, "sha256": self.sha(self.wheel)}],
        }))
        self.provenance = self.root / "build-provenance.json"
        self.provenance.write_text(json.dumps({
            "schema": "sanka.php-candidate-build/v1", "revision": self.revision,
            "artifacts": {p.name: self.sha(p) for p in (self.wheel, self.manifest)},
        }))

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def candidate(self, revision=None):
        candidate = RecordedCliCandidate(
            self.root, "php-to-fastapi", "fastapi", self.root, revision or self.revision
        )
        candidate.root = self.root
        candidate.env = {}
        return candidate

    def test_each_stage_requires_explicit_success(self):
        candidate = self.candidate()
        for stage in ("scan", "plan", "apply", "test", "verify"):
            for outcome in ("not_run", "blocked", "error", None):
                with self.subTest(stage=stage, outcome=outcome):
                    candidate.response = {"outcome": outcome}
                    with self.assertRaises(RuntimeError):
                        candidate.cli(stage)
            candidate.response = {"outcome": "success", "data": {"value": 1}}
            self.assertEqual(candidate.cli(stage), candidate.response)

    def test_bundle_requires_matching_build_provenance(self):
        self.candidate()
        with self.assertRaises(ValueError):
            self.candidate("b" * 40)
        self.provenance.unlink()
        with self.assertRaises(ValueError):
            self.candidate()

    def test_manifest_cannot_relabel_changed_wheel_bytes(self):
        self.wheel.write_bytes(b"different candidate artifact")
        manifest = json.loads(self.manifest.read_text())
        manifest["wheels"][0]["sha256"] = self.sha(self.wheel)
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.candidate()


if __name__ == "__main__":
    unittest.main()
