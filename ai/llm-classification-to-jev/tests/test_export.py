import importlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
check = importlib.import_module("check")


class ExportTests(unittest.TestCase):
    def test_preserves_candidate_evidence_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifacts = root / "artifacts"
            (artifacts / "candidate").mkdir(parents=True)
            (artifacts / "candidate/classifier.py").write_text("value = 1\n")
            for name in (
                "inventory.json",
                "migration-plan.json",
                "migration.diff",
                "compatibility-report.json",
                "verification-report.json",
            ):
                (artifacts / name).write_text("{}\n")
            output = root / "output"
            report = check.export_artifacts(artifacts, output)
            self.assertEqual(
                report["sha256"]["candidate/classifier.py"],
                check.sha(output / "candidate/classifier.py"),
            )
            self.assertEqual(len(report["sha256"]), 6)
            with self.assertRaises(ValueError):
                check.export_artifacts(artifacts, output)
            link = root / "link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                check.export_artifacts(artifacts, link / "escape")


if __name__ == "__main__":
    unittest.main()
