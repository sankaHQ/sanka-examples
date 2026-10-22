# SPDX-License-Identifier: Apache-2.0
"""Receipt comparison owns stale-result detection after actual CLI acceptance."""

import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "java_example",
    Path(__file__).resolve().parents[1] / "java/spring-greetings/check.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceTest(unittest.TestCase):
    def test_changed_acceptance_fields_are_rejected(self):
        recorded = {
            "observations": [{"body": {"number": 1}}],
            "target_runtime": {"fastapi": "0.141.1"},
            "generated_sha256": {"app.py": "a" * 64},
            "stages": {"verify": "success"},
        }
        changes = {
            "observations": [{"body": {"number": 1.0}}],
            "target_runtime": {"fastapi": "0.141.2"},
            "generated_sha256": {"app.py": "b" * 64},
            "stages": {"verify": "failed"},
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                changed = copy.deepcopy(recorded)
                changed[key] = value
                with self.assertRaises(ValueError):
                    module.compare_evidence(changed, recorded)

    def test_only_unrelated_cache_diagnostics_may_differ(self):
        module.compare_evidence(
            {
                "observations": [{"body": "ok"}],
                "source_dependencies": {"dependency_count": 400},
            },
            {
                "observations": [{"body": "ok"}],
                "source_dependencies": {"dependency_count": 322},
            },
        )
