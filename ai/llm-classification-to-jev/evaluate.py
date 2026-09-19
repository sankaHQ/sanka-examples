"""Application-owned paired evaluation. No provider import or request unless --live."""

import argparse
import ast
import hashlib
import importlib.metadata
import json
import logging
import math
import os
import random
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = {"billing", "technical", "sales", "unknown"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_request(path):
    """Read literals only; never execute the application's source."""
    tree = ast.parse(Path(path).read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "create"
    ]
    if len(calls) != 1:
        raise ValueError("Expected exactly one source responses.create call")
    return {k.arg: ast.literal_eval(k.value) for k in calls[0].keywords if k.arg != "input"}


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(q * len(values)) - 1)]


def bootstrap_interval(values):
    """Deterministic paired mean-difference 95% bootstrap interval."""
    if not values:
        return None
    rng = random.Random(319)
    means = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000)]
    return [quantile(means, 0.025), quantile(means, 0.975)]


def token_cost(usage, rates, uncached=False):
    if usage is None:
        return None
    n = usage.get("input_tokens")
    out = usage.get("output_tokens")
    cached = usage.get("cached_input_tokens", 0)
    if any(type(v) is not int or v < 0 for v in (n, out, cached)) or cached > n:
        return None
    cached = 0 if uncached else cached
    return (
        (n - cached) * rates["input"] + cached * rates["cached_input"] + out * rates["output"]
    ) / 1e6


def validate_prediction(result, provider):
    if result.get("prediction") not in LABELS:
        raise ValueError("Malformed label")
    if provider == "jev":
        if result.get("answer_type") != "choice":
            raise ValueError("Malformed answer type")
        confidence = result.get("confidence")
        probabilities = result.get("probabilities", {})
        if (
            type(confidence) not in (float, int)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Malformed confidence")
        if set(probabilities) != LABELS or any(
            type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1
            for v in probabilities.values()
        ):
            raise ValueError("Malformed probabilities")
        if abs(sum(probabilities.values()) - 1) > 0.000001:
            raise ValueError("Malformed probability sum")
    return result


def one_decision(call, text, provider, policy):
    attempts = []
    start = time.perf_counter()
    result = None
    for index in range(1 if provider == "openai" else policy["max_attempts"]):
        attempt_start = time.perf_counter()
        observation = None
        try:
            observation = call(text)
            if observation.get("returned_model") != policy["models"][provider]:
                raise ValueError("Returned model mismatch")
            result = validate_prediction(observation, provider)
            attempt = {"number": index + 1, "status": "ok", **result}
        except Exception as exc:
            # Never serialize exceptions, SDK bodies, headers, request IDs, or credentials.
            attempt = {
                "number": index + 1,
                "status": "failed",
                "error_type": type(exc).__name__,
                "usage": observation.get("usage") if isinstance(observation, dict) else None,
                "returned_model": observation.get("returned_model")
                if isinstance(observation, dict)
                else None,
            }
        attempt["elapsed_seconds"] = time.perf_counter() - attempt_start
        attempts.append(attempt)
        if attempt["status"] == "ok" or observation is not None:
            # A received malformed result abstains immediately, like the adapter.
            break
    if hasattr(call, "close_decision"):
        call.close_decision()
    accepted = (
        result is not None
        and result["prediction"] != "unknown"
        and (provider == "openai" or result["confidence"] >= policy["confidence_threshold"])
    )
    return {
        "attempts": attempts,
        "prediction": result["prediction"] if accepted else "unknown",
        "accepted": accepted,
        "failed": result is None,
        "elapsed_seconds": time.perf_counter() - start,
    }


def metrics(rows):
    n = len(rows)
    accepted = [r for r in rows if r["accepted"]]
    wrong = sum(r["prediction"] != r["expected"] for r in accepted)
    return {
        "cases": n,
        "accepted": len(accepted),
        "acceptance_coverage": len(accepted) / n if n else None,
        "review_rate": 1 - len(accepted) / n if n else None,
        "accepted_accuracy": 1 - wrong / len(accepted) if accepted else None,
        "false_match_rate": wrong / n if n else None,
        "failure_rate": sum(r["failed"] for r in rows) / n if n else None,
        "latency_median_seconds": statistics.median([r["elapsed_seconds"] for r in rows])
        if n
        else None,
        "latency_p95_seconds": quantile([r["elapsed_seconds"] for r in rows], 0.95),
    }


def summarize(records, policy, mode, split):
    summary = {}
    for row in records:
        for attempt in row["attempts"]:
            attempt["rate_card_usd"] = token_cost(
                attempt.get("usage"), policy["rate_card"][row["provider"]]
            )
            attempt["rate_card_usd_all_uncached"] = token_cost(
                attempt.get("usage"), policy["rate_card"][row["provider"]], True
            )
        for uncached, suffix in ((False, ""), (True, "_all_uncached")):
            amounts = [
                token_cost(a.get("usage"), policy["rate_card"][row["provider"]], uncached)
                for a in row["attempts"]
            ]
            row["rate_card_usd" + suffix] = (
                sum(amounts) if amounts and None not in amounts else None
            )
    for provider in ("openai", "jev"):
        rows = [r for r in records if r["provider"] == provider]
        summary[provider] = {
            "overall": metrics(rows),
            "slices": {
                key: metrics([r for r in rows if r["language"] == key or r["slice"] == key])
                for key in ("en", "ja", "ordinary", "ambiguous", "unknown", "adversarial")
            },
        }
        for uncached, suffix in ((False, ""), (True, "_all_uncached")):
            costs = [
                token_cost(a.get("usage"), policy["rate_card"][provider], uncached)
                for r in rows
                for a in r["attempts"]
            ]
            summary[provider]["rate_card_usd" + suffix] = (
                sum(costs) if costs and None not in costs else None
            )
            summary[provider]["rate_card_usd_per_decision" + suffix] = (
                (sum(costs) / len(rows)) if rows and costs and None not in costs else None
            )
    by_id = {}
    for r in records:
        by_id.setdefault(r["case_id"], {})[r["provider"]] = r
    pairs = [x for x in by_id.values() if set(x) == {"jev", "openai"}]
    latency_delta = [p["jev"]["elapsed_seconds"] - p["openai"]["elapsed_seconds"] for p in pairs]
    cost_deltas = []
    uncached_deltas = []
    for pair in pairs:
        for uncached, target in ((False, cost_deltas), (True, uncached_deltas)):
            costs = {
                p: [
                    token_cost(a.get("usage"), policy["rate_card"][p], uncached)
                    for a in pair[p]["attempts"]
                ]
                for p in pair
            }
            if all(None not in values for values in costs.values()):
                target.append(sum(costs["jev"]) - sum(costs["openai"]))
    intervals = {
        "latency_seconds": bootstrap_interval(latency_delta),
        "rate_card_usd": bootstrap_interval(cost_deltas),
        "rate_card_usd_all_uncached": bootstrap_interval(uncached_deltas),
    }
    criteria = policy["criteria"]
    complete = bool(pairs) and len(cost_deltas) == len(pairs)
    models_match = all(
        a.get("returned_model") == policy["models"][r["provider"]]
        for r in records
        for a in r["attempts"]
    )
    economics_pass = (
        mode == "live"
        and complete
        and models_match
        and len(pairs) >= criteria["min_pairs"]
        and all(v is not None and v[1] < 0 for v in intervals.values())
        and summary["jev"]["overall"]["latency_p95_seconds"]
        < summary["openai"]["overall"]["latency_p95_seconds"]
    )
    quality = summary["jev"]["overall"]
    quality_pass = (
        mode == "live"
        and split == "heldout"
        and len(pairs) >= criteria["min_pairs"]
        and quality["accepted_accuracy"] is not None
        and quality["accepted_accuracy"] >= criteria["min_accepted_accuracy"]
        and quality["false_match_rate"] <= criteria["max_false_match_rate"]
        and quality["acceptance_coverage"] >= criteria["min_acceptance_coverage"]
        and quality["failure_rate"] <= criteria["max_failure_rate"]
    )
    return {
        "providers": summary,
        "pairs": len(pairs),
        "paired_mean_delta_95pct_bootstrap": intervals,
        "cost_accounting_complete": complete,
        "returned_models_match": models_match,
        "economics_gate": "passed" if economics_pass else "inconclusive_or_failed",
        "quality_gate": "passed" if quality_pass else "not_accepted",
        "latency_kind": "complete_decision_wall_clock"
        if mode == "live"
        else "mock_local_execution_not_provider_latency",
        "cost_kind": policy["rate_card"]["kind"],
    }


def validate_inputs(dataset, policy, split, live):
    if not 1 <= policy["max_attempts"] <= 3 or not 0 < policy["timeout_seconds"] <= 30:
        raise ValueError("Evaluation attempts/timeout outside bounded limits")
    if not 0 <= policy["confidence_threshold"] <= 1:
        raise ValueError("Invalid confidence threshold")
    cases = dataset["cases"]
    if len({r["id"] for r in cases}) != len(cases) or len({r["text"] for r in cases}) != len(cases):
        raise ValueError("Duplicate case IDs or texts across splits")
    if any(
        r["split"] not in {"calibration", "heldout"} or r["expected"] not in LABELS for r in cases
    ):
        raise ValueError("Invalid dataset split or label")
    if live:
        if any(
            x.get("review_status") != "human_reviewed" or not x.get("reviewer")
            for x in (dataset, policy)
        ):
            raise ValueError("Live evaluation requires human-reviewed labels and policy")
        if split == "heldout" and (
            policy["threshold_status"] != "calibrated"
            or policy["calibration_dataset_sha256"]
            != canonical_digest([r for r in cases if r["split"] == "calibration"])
        ):
            raise ValueError(
                "Held-out evaluation requires threshold locked against calibration data"
            )
    selected = [r for r in cases if r["split"] == split]
    if not selected or len(selected) > min(policy["max_cases"], 100):
        raise ValueError("Empty dataset or case limit exceeded")
    return selected


def validate_decision(decision, policy, source, request):
    tree = ast.parse(source.read_text())
    call = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "create"
    )
    if (
        decision.get("schema_version") != "sanka-jev-decision/v1"
        or decision["source"]["sha256"] != digest(source)
        or decision["source"]["file"] != "classifier.py"
        or decision["source"]["function"] != "classify"
        or decision["source"]["call_site"] != f"classifier.py:classify:{call.lineno}"
        or decision["source"]["adapter"] != "openai-responses-enum/v1"
        or decision["state"] != {"projection": "text", "input_name": "text"}
        or decision["contract"]["input"] != {"name": "text", "type": "str"}
        or set(decision["contract"]["return"]["labels"]) != LABELS
        or {x["id"] for x in decision["question"]["options"]} != LABELS
        or decision["abstention"]["label"] != "unknown"
        or decision["fallback"]["label"] != "unknown"
    ):
        raise ValueError("Decision/source contract mismatch")
    target = decision["target"]
    if (
        request["model"] != policy["models"]["openai"]
        or target["model"] != policy["models"]["jev"]
        or target["sdk"] != "typesafe-sdk==0.7.0"
        or target["credential_env"] != "TYPESAFE_API_KEY"
        or target["timeout_seconds"] != policy["timeout_seconds"]
        or target["max_attempts"] != policy["max_attempts"]
        or decision["confidence"]["threshold"] != policy["confidence_threshold"]
    ):
        raise ValueError("Decision/evaluation policy drift")


def live_clients(policy, request, decision):
    # Pin official endpoints explicitly. Do not inherit SDK base-URL overrides.
    from openai import OpenAI
    from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

    for logger in ("openai", "typesafe_sdk", "httpx", "httpx2", "httpcore"):
        logging.getLogger(logger).disabled = True
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("TYPESAFE_API_KEY"):
        raise ValueError("Required provider credential environment variables are not set")

    # The before application owns one global OpenAI client.
    openai_client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url="https://api.openai.com/v1",
        timeout=policy["timeout_seconds"],
        max_retries=0,
    )
    jev_client = None
    jev_choice = None

    def openai_call(text):
        response = openai_client.responses.create(input=text, **request)
        usage = response.usage
        cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0)
        result = {
            "returned_model": response.model,
            "confidence": None,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cached_input_tokens": cached,
            },
        }
        try:
            result["prediction"] = json.loads(response.output_text)["department"]
        except (ValueError, KeyError, TypeError):
            result["prediction"] = None
        return result

    def jev_call(text):
        nonlocal jev_client, jev_choice
        question = decision["question"]
        # Match the generated adapter: one client per complete decision, shared across retries.
        if jev_client is None:
            jev_choice = Choice(
                instructions=question["text"],
                criteria={x["id"]: x["description"] for x in question["options"]},
            )
            jev_client = TypeSafeClient(
                api_key=os.environ["TYPESAFE_API_KEY"],
                base_url="https://api.typesafe.ai",
                model=policy["models"]["jev"],
                timeout=policy["timeout_seconds"],
                retry=RetryPolicy(max_retries=0),
            )
        response = jev_client.system_one(
            state=text, model=policy["models"]["jev"], questions={question["id"]: jev_choice}
        )
        result = {
            "prediction": None,
            "returned_model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cached_input_tokens": 0,
                "cache_reporting": "not_reported_by_provider",
            },
        }
        answer = response.answers.get(question["id"])
        if answer is not None:
            result.update(
                answer_type=getattr(answer, "type", None),
                prediction=getattr(answer, "choice", None),
                confidence=getattr(answer, "confidence", None),
                probabilities=getattr(answer, "probabilities", {}),
            )
        return result

    def close_jev():
        nonlocal jev_client
        if jev_client is not None:
            try:
                jev_client.close()
            except Exception:
                pass
            jev_client = None

    jev_call.close_decision = close_jev
    jev_call.close = close_jev
    return {"openai": openai_call, "jev": jev_call}, (openai_client, jev_call)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Explicitly enable bounded paid provider requests"
    )
    parser.add_argument("--split", choices=("calibration", "heldout"), default="calibration")
    parser.add_argument("--dataset", type=Path, default=ROOT / "fixtures/dataset.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "evaluation-policy.json")
    parser.add_argument("--decision", type=Path, default=ROOT / "source/jev-decision.json")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    atomic_report(args.report, {"status": "incomplete", "mode": "live" if args.live else "mock"})
    try:
        execute(args)
    except Exception as exc:
        atomic_report(args.report, {"status": "failed", "error_type": type(exc).__name__})
        raise


def atomic_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute(args):
    dataset = json.loads(args.dataset.read_text())
    policy = json.loads(args.policy.read_text())
    decision = json.loads(args.decision.read_text())
    cases = validate_inputs(dataset, policy, args.split, args.live)
    request = source_request(ROOT / "source/classifier.py")
    validate_decision(decision, policy, ROOT / "source/classifier.py", request)
    clients = ()
    if args.live:
        calls, clients = live_clients(policy, request, decision)
    else:
        # Fixed mock outputs deliberately do not use expected labels as model predictions.
        calls = {
            p: lambda text, p=p: {
                "prediction": "unknown",
                "answer_type": "choice",
                "confidence": 0.2,
                "probabilities": dict.fromkeys(sorted(LABELS), 0.25),
                "returned_model": policy["models"][p],
                "usage": None,
            }
            for p in ("openai", "jev")
        }
    start = datetime.now(timezone.utc).isoformat()
    records = []
    try:
        for index, case in enumerate(cases):
            # Alternate order by pair to reduce a systematic first-provider effect.
            for provider in ("openai", "jev") if index % 2 == 0 else ("jev", "openai"):
                records.append(
                    {
                        "case_id": case["id"],
                        "expected": case["expected"],
                        "language": case["language"],
                        "slice": case["slice"],
                        "provider": provider,
                        "request_order": len(records) + 1,
                        **one_decision(calls[provider], case["text"], provider, policy),
                    }
                )
    finally:
        for client in clients:
            client.close()
    report = {
        "schema_version": 1,
        "mode": "live" if args.live else "mock",
        "split": args.split,
        "started_at": start,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "provider_region": "unknown",
        "provider_tier": "unknown",
        "dataset_sha256": digest(args.dataset),
        "decision_sha256": digest(args.decision),
        "policy_sha256": digest(args.policy),
        "source_sha256": digest(ROOT / "source/classifier.py"),
        "prompt_sha256": canonical_digest({"openai": request, "jev": decision}),
        "models_requested": policy["models"],
        "label_review_status": dataset["review_status"],
        "threshold_status": policy["threshold_status"],
        "records": records,
        "summary": summarize(records, policy, "live" if args.live else "mock", args.split),
    }
    report["sdk_versions"] = (
        {p: importlib.metadata.version(p) for p in ("openai", "typesafe-sdk")} if args.live else {}
    )
    report["status"] = "completed"
    atomic_report(args.report, report)
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "report": str(args.report),
                "economics_gate": report["summary"]["economics_gate"],
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print provider exceptions or credential-bearing configuration.
        raise SystemExit("Evaluation failed: " + type(exc).__name__) from None
