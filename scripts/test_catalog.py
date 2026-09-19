# SPDX-License-Identifier: Apache-2.0
"""Reject missing stage evidence and stale fixture identities in the runnable catalog."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from check_catalog import validate


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "express/status-api"
        self.directory.mkdir(parents=True)
        (self.directory / "README.md").write_text("example")
        (self.directory / "LICENSE").write_text("Apache-2.0")
        (self.directory / "app.ts").write_text("source")
        self.metadata = {
            "schema": "sanka-examples/migration/v1",
            "id": "express/status-api",
            "source": {"language": "typescript", "framework": "express"},
            "destinations": [
                {
                    "language": "rust",
                    "framework": "axum",
                    "extension_id": "sanka/typescript-to-rust",
                    "candidate_revision": "a" * 40,
                    "release_status": "experimental-unpublished",
                    "supported_stages": ["scan", "plan", "apply", "test", "verify"],
                }
            ],
            "license": "Apache-2.0",
            "provenance": "synthetic",
        }
        self.evidence = {
            "status": "passed",
            "source_preserved": True,
            "candidate": {
                "extension_revision": "a" * 40,
                "extension_id": "sanka/typescript-to-rust",
            },
            "stages": {
                s: "passed" for s in ["scan", "plan", "apply", "test", "verify"]
            },
            "source_sha256": {"app.ts": hashlib.sha256(b"source").hexdigest()},
            "generated_sha256": {"src/main.rs": "b" * 64},
        }

    def write(self):
        (self.root / "manifest.json").write_text(
            json.dumps({"schema": "sanka-examples/manifest/v1"})
        )
        (self.directory / "migration.json").write_text(json.dumps(self.metadata))
        (self.directory / "evidence.json").write_text(json.dumps(self.evidence))
        entry = {k: self.metadata[k] for k in ("id", "source", "destinations")}
        entry.update(status="checked-in", evidence="evidence.json")
        (self.root / "migrations.json").write_text(
            json.dumps(
                {
                    "schema": "sanka-examples/migrations/v1",
                    "examples": [entry],
                    "planned": [],
                }
            )
        )

    def test_pass(self):
        self.write()
        validate(self.root)

    def test_separately_tracked_cookbook_must_exist(self):
        self.write()
        path = self.root / "migrations.json"
        index = json.loads(path.read_text())
        index["separately_tracked"] = [
            {
                "id": "ai/classifier",
                "status": "tracked-separately",
                "readme": "ai/classifier/README.md",
            }
        ]
        path.write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError, "cookbook must exist"):
            validate(self.root)
        readme = self.root / "ai/classifier/README.md"
        readme.parent.mkdir(parents=True)
        readme.write_text("separate acceptance")
        validate(self.root)

    def test_failed_or_missing_stages(self):
        for stage in self.evidence["stages"]:
            with self.subTest(stage=stage):
                self.evidence["stages"][stage] = "not_run"
                self.write()
                with self.assertRaisesRegex(ValueError, "Stage not passed"):
                    validate(self.root)
                self.evidence["stages"][stage] = "passed"
        self.evidence["status"] = "failed"
        self.write()
        with self.assertRaisesRegex(ValueError, "Failed acceptance"):
            validate(self.root)

    def test_missing_source_identity(self):
        self.metadata["source"] = {}
        self.write()
        with self.assertRaisesRegex(ValueError, "Missing source"):
            validate(self.root)

    def test_published_release_requires_public_evidence(self):
        destination = self.metadata["destinations"][0]
        destination.update(
            release_status="experimental-published",
            release_revision="c" * 40,
            release_tag="api-converters-v0.1.0a1",
            manifest_sha256="d" * 64,
        )
        self.write()
        with self.assertRaisesRegex(ValueError, "Published release evidence"):
            validate(self.root)
        self.evidence["candidate"].update(
            release_status="experimental-published",
            extension_revision="c" * 40,
            release_tag="api-converters-v0.1.0a1",
            manifest_sha256="d" * 64,
            wheels={"converter.whl": "e" * 64},
        )
        self.write()
        validate(self.root)

    def test_wrong_candidate(self):
        self.evidence["candidate"]["extension_revision"] = "b" * 40
        self.write()
        with self.assertRaisesRegex(ValueError, "Candidate identity"):
            validate(self.root)

    def test_stale_source(self):
        self.write()
        (self.directory / "app.ts").write_text("changed source")
        with self.assertRaisesRegex(ValueError, "Stale source"):
            validate(self.root)

    def test_compose_cannot_claim_apply(self):
        self.metadata["destinations"][0]["framework"] = "compose"
        self.write()
        with self.assertRaisesRegex(ValueError, "Compose is scan/plan only"):
            validate(self.root)


if __name__ == "__main__":
    unittest.main()
