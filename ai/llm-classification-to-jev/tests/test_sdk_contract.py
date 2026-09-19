"""Real pinned SDK serializers over in-memory transports; never contacts providers."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
evaluate = importlib.import_module("evaluate")


@unittest.skipUnless(
    importlib.util.find_spec("typesafe_sdk") and importlib.util.find_spec("openai"),
    "Install requirements-evaluation.txt for real SDK serialization checks",
)
class SDKContractTests(unittest.TestCase):
    def test_serialization_usage_and_malformed_answer(self):
        import httpx2
        import openai
        import typesafe_sdk

        self.assertEqual(openai.__version__, "3.16.2")
        self.assertEqual(typesafe_sdk.__version__, "0.7.0")
        policy = json.loads((ROOT / "evaluation-policy.json").read_text())
        decision = json.loads((ROOT / "source/jev-decision.json").read_text())
        seen = []
        malformed = [False]

        def jev_transport(request):
            body = json.loads(request.content)
            self.assertEqual(str(request.url), "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(body["model"], "jev-1.13.0")
            self.assertEqual(body["questions"]["department"]["type"], "choice")
            seen.append(body)
            return httpx2.Response(
                200,
                json={
                    "model": "jev-1.13.0",
                    "usage": {"input_tokens": 123, "output_tokens": 8},
                    "answers": {
                        "wrong" if malformed[0] else "department": {
                            "type": "choice",
                            "choice": "billing",
                            "confidence": 0.95,
                            "probabilities": {
                                "billing": 0.97,
                                "sales": 0.01,
                                "technical": 0.01,
                                "unknown": 0.01,
                            },
                        }
                    },
                },
            )

        def openai_transport(request):
            body = json.loads(request.content)
            self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
            self.assertEqual(body["model"], "gpt-5.6-luna")
            seen.append(body)
            return httpx2.Response(
                200,
                json={
                    "id": "resp_mock",
                    "object": "response",
                    "created_at": 1,
                    "model": "gpt-5.6-luna",
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_mock",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"department":"billing"}',
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                    "usage": {
                        "input_tokens": 50,
                        "output_tokens": 5,
                        "total_tokens": 55,
                        "input_tokens_details": {"cached_tokens": 20},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                },
            )

        real_openai, real_jev = openai.OpenAI, typesafe_sdk.TypeSafeClient

        def openai_factory(**kwargs):
            self.assertEqual(kwargs["max_retries"], 0)
            return real_openai(
                **kwargs,
                http_client=httpx2.Client(transport=httpx2.MockTransport(openai_transport)),
            )

        def jev_factory(**kwargs):
            self.assertEqual(kwargs["retry"].max_retries, 0)
            return real_jev(**kwargs, transport=httpx2.MockTransport(jev_transport))

        with (
            patch.dict(
                "os.environ", {"OPENAI_API_KEY": "offline-test", "TYPESAFE_API_KEY": "offline-test"}
            ),
            patch.object(openai, "OpenAI", openai_factory),
            patch.object(typesafe_sdk, "TypeSafeClient", jev_factory),
        ):
            calls, clients = evaluate.live_clients(
                policy, evaluate.source_request(ROOT / "source/classifier.py"), decision
            )
            try:
                a = calls["openai"]("請求書を送ってください。")
                b = calls["jev"]("請求書を送ってください。")
                self.assertEqual(a["usage"]["cached_input_tokens"], 20)
                self.assertEqual(b["usage"]["input_tokens"], 123)
                self.assertEqual(a["prediction"], b["prediction"])
                malformed[0] = True
                failed = evaluate.one_decision(calls["jev"], "x", "jev", policy)
                self.assertTrue(failed["failed"])
                self.assertEqual(failed["attempts"][0]["usage"]["input_tokens"], 123)
                self.assertEqual(len(seen), 3)
            finally:
                for client in clients:
                    client.close()


if __name__ == "__main__":
    unittest.main()
