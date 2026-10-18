import argparse
import json
import secrets
import sys
import time
import urllib.request
from uuid import UUID

from scripts.chaos_latency import request, summarize, utc, validate_url


EXPERIMENT = "data-service-errors-10pct-v1"


def run_errors(args):
    base = validate_url(args.base_url)
    application_id = str(UUID(args.application_id))

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, target):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    url = base + "/credit-applications/" + application_id
    setup_trace = format((int(time.time()) << 96 | secrets.randbits(96)) & ~0xFFFF0000, "032x")
    setup, body = request(opener, "GET", url, trace_id=setup_trace)
    if setup["status"] != 200 or not body or body.get("application_id") != application_id:
        raise RuntimeError("Known synthetic record not readable; no data will be created or changed")
    print(json.dumps({"event": "chaos.setup.complete", **setup, "application_id": application_id}), flush=True)
    phases = {}
    samples = []
    for phase in ["baseline", "injection", "recovery"]:
        phases[phase] = {"started_utc": utc()}
        print(json.dumps({"event": "chaos.phase.started", "phase": phase, "utc": phases[phase]["started_utc"]}), flush=True)
        started = time.monotonic()
        sequence = 0
        while time.monotonic() - started < args.phase_seconds:
            request_started = time.monotonic()
            sequence += 1
            if phase == "injection":
                trace_id = format(int(time.time()), "08x") + secrets.token_hex(8) + "e220" + format(sequence, "04x")
            else:
                trace_id = format((int(time.time()) << 96 | secrets.randbits(96)) & ~0xFFFF0000, "032x")
            sample, _ = request(opener, "GET", url, trace_id=trace_id)
            sample.update(phase=phase, sequence=sequence)
            samples.append(sample)
            print(json.dumps(sample), flush=True)
            time.sleep(max(0, min(request_started + 1 / args.rps, started + args.phase_seconds) - time.monotonic()))
        rows = [s for s in samples if s["phase"] == phase]
        phases[phase].update(ended_utc=utc(), **summarize(rows, 0.995, 1000))
        phases[phase]["http_status_counts"] = {str(code): sum(s["status"] == code for s in rows) for code in sorted({s["status"] for s in rows})}
        print(json.dumps({"event": "chaos.phase.finished", "phase": phase, **phases[phase]}), flush=True)
    summary = {"event": "chaos.summary", "experiment": EXPERIMENT, "environment": args.environment,
               "requested_error_percent": 10, "schedule": "deterministic: each tenth eligible data-service attempt; proxy retries may hide failures from the client",
               "rps_limit": args.rps, "phase_seconds": args.phase_seconds, "phases": phases,
               "application_id": application_id, "data_writes": 0, "mttd_alert_seconds": None,
               "slo": {"target": 0.995, "latency_threshold_ms": 1000, "scope": "GET requests in this experiment, not monthly budget"}}
    print(json.dumps(summary), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--phase-seconds", type=float, default=180)
    parser.add_argument("--rps", type=float, default=3)
    parser.add_argument("--environment", choices=["local", "aws"], default="local")
    args = parser.parse_args()
    if not 0 < args.phase_seconds <= 300 or not 0 < args.rps <= 3:
        parser.error("Use phase seconds in (0,300] and RPS in (0,3]")
    run_errors(args)
