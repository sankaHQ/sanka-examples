# SPDX-License-Identifier: Apache-2.0
"""Failure evidence and lock preservation are part of the release contract."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check.py"
spec = importlib.util.spec_from_file_location("acceptance", SCRIPT)
assert spec is not None and spec.loader is not None
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class AcceptanceTests(unittest.TestCase):
    def test_failed_candidate_overwrites_stale_success_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "invalid.whl"
            wheel.write_bytes(b"not a wheel")
            report = root / "report.json"
            report.write_text('{"status":"passed"}')
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--cli-wheel", str(wheel), "--report", str(report)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertNotEqual(result.returncode, 0)
            evidence = json.loads(report.read_text())
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["stage"], "candidate selection")
            self.assertIn("BadZipFile", evidence["error"])

    def test_candidate_must_identify_sanka_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "other.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("other.dist-info/METADATA", "Name: other\nVersion: 0.2.13\n")
            with self.assertRaisesRegex(ValueError, "sanka-cli"):
                acceptance.wheel_identity(wheel)

    def test_changed_lock_is_a_failure_even_when_json_is_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "extensions.lock"
            before = b'{"extensions": []}\n'
            lock.write_bytes(before)
            self.assertEqual(len(acceptance.verify_lock(lock, before)), 64)
            lock.write_bytes(b'{ "extensions": [] }\n')
            with self.assertRaisesRegex(AssertionError, "changed.*lock"):
                acceptance.verify_lock(lock, before)
