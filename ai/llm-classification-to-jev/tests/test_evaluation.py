import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
evaluate = importlib.import_module("evaluate")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "evaluation-policy.json").read_text())
        self.dataset = json.loads((ROOT / "fixtures/dataset.json").read_text())

    def test_splits_and_review_gate(self):
        for split in ("calibration", "heldout"):
            cases = evaluate.validate_inputs(self.dataset, self.policy, split, False)
            self.assertEqual(len(cases), 12)
            self.assertEqual({c["language"] for c in cases}, {"en", "ja"})
            self.assertEqual(
                {c["slice"] for c in cases}, {"ordinary", "unknown", "ambiguous", "adversarial"}
            )
        with self.assertRaises(ValueError):
            evaluate.validate_inputs(self.dataset, self.policy, "calibration", True)
        for item in (self.dataset, self.policy):
            item.update(review_status="human_reviewed", reviewer="test fixture")
        with self.assertRaises(ValueError):
            evaluate.validate_inputs(self.dataset, self.policy, "heldout", True)

    def test_source_literals_without_import(self):
        request = evaluate.source_request(ROOT / "source/classifier.py")
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(
            set(request["text"]["format"]["schema"]["properties"]["department"]["enum"]),
            evaluate.LABELS,
        )

    def test_all_unknown_cannot_pass(self):
        rows = [
            {
                "prediction": "unknown",
                "expected": "billing",
                "accepted": False,
                "failed": False,
                "elapsed_seconds": 0.0,
            }
        ]
        report = evaluate.metrics(rows)
        self.assertIsNone(report["accepted_accuracy"])
        self.assertEqual(report["acceptance_coverage"], 0)
        self.assertEqual(report["review_rate"], 1)

    def test_retry_accounts_for_failed_attempt_and_hides_exception(self):
        attempts = []

        def fail_once(text):
            attempts.append(text)
            if len(attempts) == 1:
                raise TimeoutError("secret must never be serialized")
            return {
                "prediction": "billing",
                "returned_model": "gpt-5.6-luna",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }

        self.policy["max_attempts"] = 2
        result = evaluate.one_decision(fail_once, "example", "openai", self.policy)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertIsNone(result["attempts"][0]["usage"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertTrue(result["accepted"])

    def test_invalid_confidence_fails_with_recorded_usage(self):
        response = {
            "prediction": "billing",
            "confidence": float("nan"),
            "probabilities": dict.fromkeys(evaluate.LABELS, 0.25),
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }
        result = evaluate.one_decision(lambda _: response, "x", "jev", self.policy)
        self.assertTrue(result["failed"])
        self.assertEqual(result["attempts"][0]["usage"], response["usage"])
        self.assertEqual(result["prediction"], "unknown")

    def test_cache_and_unknown_cost(self):
        usage = {"input_tokens": 1000, "output_tokens": 20, "cached_input_tokens": 900}
        rates = self.policy["rate_card"]["openai"]
        self.assertLess(evaluate.token_cost(usage, rates), evaluate.token_cost(usage, rates, True))
        self.assertIsNone(evaluate.token_cost(None, rates))
        self.assertIsNone(evaluate.token_cost({**usage, "cached_input_tokens": 2000}, rates))

    def test_mock_and_insufficient_pairs_never_accept(self):
        rows = []
        for provider in ("openai", "jev"):
            rows.append(
                {
                    "case_id": "one",
                    "provider": provider,
                    "language": "en",
                    "slice": "ordinary",
                    "expected": "billing",
                    "prediction": "billing",
                    "accepted": True,
                    "failed": False,
                    "elapsed_seconds": 0.1 if provider == "jev" else 1,
                    "attempts": [
                        {
                            "usage": {"input_tokens": 10, "output_tokens": 1},
                            "returned_model": self.policy["models"][provider],
                        }
                    ],
                }
            )
        for mode in ("mock", "live"):
            result = evaluate.summarize(rows, self.policy, mode, "heldout")
            self.assertNotEqual(result["economics_gate"], "passed")
            self.assertNotEqual(result["quality_gate"], "passed")

    def test_prediction_parity_and_no_malformed_retry(self):
        response = {
            "prediction": "billing",
            "answer_type": "choice",
            "confidence": 0.95,
            "probabilities": {"billing": 0.97, "sales": 0.01, "technical": 0.01, "unknown": 0.01},
            "returned_model": "jev-1.13.0",
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }
        self.policy["max_attempts"] = 2
        for change in (
            {},
            {"returned_model": "wrong"},
            {"answer_type": "noul"},
            {
                "probabilities": {
                    "billing": 0.975,
                    "sales": 0.01,
                    "technical": 0.01,
                    "unknown": 0.01,
                }
            },
        ):
            call = unittest.mock.Mock(return_value={**response, **change})
            result = evaluate.one_decision(call, "x", "jev", self.policy)
            self.assertEqual(result["accepted"], not bool(change))
            self.assertEqual(call.call_count, 1)
            call.close_decision.assert_called_once_with()
            self.assertEqual(result["attempts"][0]["usage"], response["usage"])

    def test_policy_drift(self):
        decision = json.loads((ROOT / "source/jev-decision.json").read_text())
        source = ROOT / "source/classifier.py"
        evaluate.validate_decision(decision, self.policy, source, evaluate.source_request(source))
        self.policy["confidence_threshold"] = 0.2
        with self.assertRaises(ValueError):
            evaluate.validate_decision(
                decision, self.policy, source, evaluate.source_request(source)
            )

    def test_failed_run_replaces_previous_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            report.write_text('{"status":"completed","summary":{"economics_gate":"passed"}}')
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "evaluate.py"),
                    "--dataset",
                    str(Path(tmp) / "missing.json"),
                    "--report",
                    str(report),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                json.loads(report.read_text()),
                {"status": "failed", "error_type": "FileNotFoundError"},
            )
            self.assertNotIn("passed", report.read_text())

    def test_source_contract_with_injected_provider(self):
        response = types.SimpleNamespace(output_text='{"department":"billing"}')
        create = unittest.mock.Mock(return_value=response)
        fake = types.ModuleType("openai")
        fake.OpenAI = lambda **_: types.SimpleNamespace(
            responses=types.SimpleNamespace(create=create)
        )
        with patch.dict(sys.modules, {"openai": fake}):
            spec = importlib.util.spec_from_file_location(
                "fixture_classifier", ROOT / "source/classifier.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertEqual(module.classify("請求書について相談があります。"), "billing")
        self.assertEqual(create.call_args.kwargs["input"], "請求書について相談があります。")
        for failure in (TimeoutError(), RuntimeError()):
            create.side_effect = failure
            self.assertEqual(module.classify("test"), "unknown")
        create.side_effect = None
        response.output_text = "not json"
        self.assertEqual(module.classify("test"), "unknown")


if __name__ == "__main__":
    unittest.main()
