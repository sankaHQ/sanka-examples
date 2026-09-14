# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from example_config_upgrade import EXTENSION_ID, VERSION, handle
from sanka_extensions.code import ExtensionRequest, decode_response, encode_response


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.source = self.project / "example-app.json"
        self.source.write_text('{"schema_version": 1, "title": "Orders"}')

    def request(self, command="plan"):
        return ExtensionRequest(
            request_id="test-request",
            command=command,
            project_root=str(self.project),
            artifact_root=str(self.root / "artifacts"),
            extension_id=EXTENSION_ID,
            extension_version=VERSION,
            manifest_digest="a" * 64,
            fingerprint={},
            configuration={},
            prior_artifacts=(),
            reviewed_plan_hash=None,
        )

    def test_plan_matches_input_and_preserves_source(self):
        before = self.source.read_bytes()
        response = decode_response(encode_response(handle(self.request())))
        self.assertEqual(response.outcome, "success")
        self.assertEqual(response.request_id, "test-request")
        plan = json.loads(Path(response.artifacts[0]).read_text())
        self.assertEqual(plan["proposed"], {"schema_version": 2, "name": "Orders"})
        self.assertEqual(self.source.read_bytes(), before)
        first_hash = response.data["plan_hash"]
        self.source.write_text('{"schema_version": 1, "title": "Changed"}')
        self.assertNotEqual(handle(self.request()).data["plan_hash"], first_hash)

    def test_invalid_input_and_unsupported_commands_do_not_create_artifacts(self):
        for content in [
            "{}",
            "[]",
            "not JSON",
            '{"schema_version": true, "title": "X"}',
            '{"schema_version": 1, "title": "X", "extra": 1}',
        ]:
            with self.subTest(content=content):
                self.source.write_text(content)
                self.assertEqual(handle(self.request()).error.code, "EXAMPLE_INVALID_INPUT")
        for command in ("apply", "test", "verify"):
            self.assertEqual(
                handle(self.request(command)).error.code, "EXAMPLE_UNSUPPORTED_COMMAND"
            )
        self.assertFalse((self.root / "artifacts").exists())

    def test_source_and_artifact_symlinks_cannot_escape(self):
        outside = self.root / "outside.json"
        outside.write_bytes(self.source.read_bytes())
        self.source.unlink()
        self.source.symlink_to(outside)
        self.assertEqual(handle(self.request()).error.code, "EXAMPLE_INVALID_INPUT")
        self.source.unlink()
        self.source.write_bytes(outside.read_bytes())
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        (artifacts / "config-plan.json").symlink_to(outside)
        before = outside.read_bytes()
        self.assertEqual(handle(self.request()).error.code, "EXAMPLE_INVALID_INPUT")
        self.assertEqual(outside.read_bytes(), before)

    def test_malformed_transport_has_no_protocol_stdout(self):
        executable = Path(sys.executable).parent / "example-sanka-config-upgrade"
        result = subprocess.run(
            [str(executable)], input='{"bad":true}', text=True, capture_output=True, timeout=10
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Invalid extension request", result.stderr)
