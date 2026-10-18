import argparse
import contextlib
import ipaddress
import json
import math
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


EXPERIMENT = "service-b-latency-200ms-v1"


def utc():
    return datetime.now(timezone.utc).isoformat()


def percentile(values, fraction=0.99):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(samples, target, latency_ms):
    count = len(samples)
    errors = sum(sample["status"] != 200 for sample in samples)
    bad = sum(sample["status"] != 200 or sample["duration_ms"] > latency_ms for sample in samples)
    allowed = count * (1 - target)
    return {
        "requests": count,
        "errors": errors,
        "error_rate": errors / count if count else None,
        "p50_ms": percentile([sample["duration_ms"] for sample in samples], 0.50),
        "p95_ms": percentile([sample["duration_ms"] for sample in samples], 0.95),
        "p99_ms": percentile([sample["duration_ms"] for sample in samples]),
        "slo_bad_requests": bad,
        "allowed_bad_requests": allowed,
        "window_budget_consumption_percent": 100 * bad / allowed if allowed else None,
        "burn_rate": (bad / count) / (1 - target) if count else None,
    }


def validate_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use an HTTP origin without credentials, query or path")
    if parsed.hostname != "localhost" and not ipaddress.ip_address(parsed.hostname).is_private:
        raise ValueError("Use localhost or the current private IP of Service A")
    return value.rstrip("/")


def request(opener, method, url, payload=None, inject=False, trace_id=None):
    trace_id = trace_id or format(int(time.time()), "08x") + secrets.token_hex(12)
    headers = {"traceparent": "00-" + trace_id + "-" + secrets.token_hex(8) + "-01"}
    if inject:
        headers["x-lab-chaos-experiment"] = EXPERIMENT
    if payload is not None:
        headers["Content-Type"] = "application/json"
    data = json.dumps(payload).encode() if payload is not None else None
    started = time.perf_counter()
    body = None
    try:
        with opener.open(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=5) as response:
            status = response.status
            body = json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        status = 0
    return {"utc": utc(), "status": status, "duration_ms": (time.perf_counter() - started) * 1000, "trace_id": trace_id}, body


def run(args):
    base = validate_url(args.base_url)
    output = Path(args.output_dir) if args.output_dir != "-" else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, target):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    creation, body = request(opener, "POST", base + "/credit-applications", {
        "customer_name": "PRUEBA SINTETICA CAOS", "document_number": "LAB-CHAOS-001", "requested_amount": 1000,
    })
    if creation["status"] != 201 or not body or not body.get("application_id"):
        if output is not None:
            (output / "setup.json").write_text(json.dumps(creation, indent=2), encoding="utf-8")
        else:
            print(json.dumps({"event": "chaos.setup.failed", **creation}), flush=True)
        raise RuntimeError("Synthetic setup failed; do not retry POST automatically")
    print(json.dumps({"event": "chaos.setup.complete", **creation, "application_id": body["application_id"]}), flush=True)
    samples = []
    phases = {}
    destination = (output / "samples.jsonl").open("w", encoding="utf-8") if output is not None else contextlib.nullcontext(sys.stdout)
    with destination as evidence:
        for phase in ("baseline", "injection", "recovery"):
            phases[phase] = {"started_utc": utc()}
            print(json.dumps({"event": "chaos.phase.started", "phase": phase, "utc": phases[phase]["started_utc"]}), flush=True)
            started = time.monotonic()
            while time.monotonic() - started < args.phase_seconds:
                request_started = time.monotonic()
                sample, _ = request(opener, "GET", base + "/credit-applications/" + body["application_id"], inject=phase == "injection")
                sample["phase"] = phase
                samples.append(sample)
                evidence.write(json.dumps(sample) + "\n")
                evidence.flush()
                time.sleep(max(0, min(request_started + 1 / args.rps, started + args.phase_seconds) - time.monotonic()))
            phases[phase]["ended_utc"] = utc()
            phases[phase].update(summarize([sample for sample in samples if sample["phase"] == phase], args.slo_target, args.latency_slo_ms))
            print(json.dumps({"event": "chaos.phase.finished", "phase": phase, **phases[phase]}), flush=True)
    summary = {
        "environment": args.environment, "experiment": EXPERIMENT, "requested_delay_ms": 200,
        "configured_rps": args.rps, "phase_seconds": args.phase_seconds,
        "load_model": "single sequential client, best-effort pacing; actual throughput may be lower",
        "percentile_method": "nearest rank; descriptive sample p99, not a population SLO proof",
        "slo": {"target": args.slo_target, "latency_threshold_ms": args.latency_slo_ms, "scope": "experiment requests only; not the monthly remaining budget"},
        "phases": phases,
        "mttd_seconds": None,
        "mttd_status": "not measured: requires Camilo's real alert timestamp and confirmed injection start",
        "injection_status": "requested only: confirm chaos.latency spans, logs and counter before claiming injection",
        "synthetic_application_id": body["application_id"],
    }
    if output is not None:
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"event": "chaos.summary", **summary}), flush=True)
    return summary


def parser():
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--base-url", required=True)
    arguments.add_argument("--output-dir", required=True)
    arguments.add_argument("--environment", choices=["local", "aws"], default="local")
    arguments.add_argument("--phase-seconds", type=float, default=180)
    arguments.add_argument("--rps", type=float, default=3)
    arguments.add_argument("--slo-target", type=float, default=0.995)
    arguments.add_argument("--latency-slo-ms", type=float, default=1000)
    return arguments


if __name__ == "__main__":
    arguments = parser()
    options = arguments.parse_args()
    if not 0 < options.phase_seconds <= 300 or not 0 < options.rps <= 5 or not 0 < options.slo_target < 1 or options.latency_slo_ms <= 0:
        arguments.error("Use phase seconds in (0,300], RPS in (0,5], SLO target in (0,1) and positive latency threshold")
    run(options)
