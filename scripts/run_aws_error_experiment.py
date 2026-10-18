import argparse
import base64
import json
import subprocess
import time
import zlib
from datetime import datetime, timezone

from scripts import run_aws_latency_experiment as shared


ROOT, AWS, CLUSTER = shared.ROOT, shared.AWS, shared.CLUSTER
aws, tf, utc = shared.aws, shared.terraform, shared.utc
TAG = "chaos-errors-v2"
FLAGS = [flag for flag in shared.FLAGS if not flag.startswith("-var=api_image_tags=")] + [
    '-var=api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1","data-service":"chaos-errors-v2"}',
    "-var=chaos_expires_at=0",
]
DATA = {'aws_ecs_service.service["data-service"]', 'aws_ecs_task_definition.service["data-service"]'}


def review(path, cleanup=False):
    plan = json.loads(tf("show", "-json", path))
    changes = [r for r in plan["resource_changes"] if r["change"]["actions"] not in [["no-op"], ["read"]]]
    addresses = {r["address"] for r in changes}
    assert addresses <= DATA | shared.TEMP and (cleanup or addresses == DATA | shared.TEMP), "Unexpected plan scope; stop"
    for resource in changes:
        change = resource["change"]
        before, after = change.get("before") or {}, change.get("after") or {}
        if resource["address"] in shared.TEMP:
            assert change["actions"] == (["delete"] if cleanup else ["create"])
            continue
        if resource["type"] == "aws_ecs_service":
            assert change["actions"] == ["update"] and before["desired_count"] == after["desired_count"] == 1
            assert {k for k in set(before) | set(after) if before.get(k) != after.get(k)} == {"task_definition"}
            continue
        assert set(change["actions"]) == {"create", "delete"}
        for key in set(before) | set(after):
            if key in ["arn", "arn_without_revision", "id", "revision", "container_definitions"]:
                continue
            defaults = {"enable_fault_injection": False, "pid_mode": "", "ipc_mode": "", "tags": {}}
            old, new = before.get(key), after.get(key)
            if key in defaults:
                old = defaults[key] if old is None else old
                new = defaults[key] if new is None else new
            assert old == new, (resource["address"], key)
        old_containers = json.loads(before["container_definitions"])
        for container in json.loads(after["container_definitions"]):
            old = shared.normalized(next(c for c in old_containers if c["name"] == container["name"]))
            new = shared.normalized(container)
            if container["name"] == "collector":
                assert old == new and new["image"].endswith("/collector:traces-v2")
                continue
            assert container["name"] == "data-service"
            old_image, new_image = old.pop("image"), new.pop("image")
            assert old_image.endswith("/api:chaos-errors-v1") or old_image.endswith("/api:" + TAG)
            assert new_image.endswith("/api:" + TAG)
            old_env, new_env = old.pop("environment"), new.pop("environment")
            assert old == new
            strip = lambda env: [e for e in env if not e["name"].startswith("DATA_CHAOS_")]
            assert strip(old_env) == strip(new_env)
            assert bool([e for e in new_env if e["name"] == "DATA_CHAOS_ENABLED" and e["value"] == "true"]) != cleanup
    result = [{"address": r["address"], "actions": r["change"]["actions"]} for r in changes]
    print("REVIEWED_PLAN", json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        parser.error("Explicit --execute authorization is required")
    assert aws("sts", "get-caller-identity")["Account"] == "467866783326"
    assert all(s["desiredCount"] == s["runningCount"] == 1 for s in shared.services())
    ledger = json.loads((ROOT / "docs/evidence/integrator/aws/chaos/chaos-20261018T141822Z/setup.json").read_text())
    application_id = ledger["application_id"]
    assert ledger["status"] == 201
    run_id = "errors-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "docs/evidence/integrator/aws/chaos" / run_id
    output.mkdir(exist_ok=False)
    save = lambda name, value: (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    source = (ROOT / "scripts/chaos_latency.py").read_text().split('\nif __name__ == "__main__":')[0]
    source += "\n" + (ROOT / "scripts/chaos_errors.py").read_text().replace("from scripts.chaos_latency import request, summarize, utc, validate_url", "")
    compile(source, "error-client", "exec")
    encoded = base64.b64encode(zlib.compress(source.encode())).decode()
    command = ["python", "-c", "import base64,zlib;exec(zlib.decompress(base64.b64decode(" + repr(encoded) + ")))",
               "--base-url", "http://10.52.0.1:8000", "--application-id", application_id,
               "--phase-seconds", "180", "--rps", "2.5", "--environment", "aws"]
    assert len(json.dumps({"containerOverrides": [{"name": "synthetic", "command": command}]})) < 8192
    deadline = int(time.time()) + 1700
    metadata = {"run_id": run_id, "started_utc": utc(), "deadline_epoch": deadline, "application_id": application_id, "data_writes": 0}
    save("run.json", metadata)
    attempted, task_arn, temporary, failure = False, None, None, None
    try:
        plan = ".terraform/" + run_id + "-arm.tfplan"
        tf("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=true", "-var=data_error_expires_at=" + str(deadline),
           "-var=data_error_application_id=" + application_id, "-out=" + plan)
        save("activation-plan-summary.json", review(plan))
        attempted = True
        print("ARMING_DATA_SERVICE_ERRORS", run_id, flush=True)
        tf("apply", "-input=false", "-no-color", plan)
        save("armed-services.json", shared.wait_healthy())
        assert deadline - time.time() > 720
        temporary = json.loads(tf("output", "-json", "synthetic_test"))
        arn = aws("ecs", "list-tasks", "--cluster", CLUSTER, "--service-name", CLUSTER + "-service-a")["taskArns"][0]
        task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", arn)["tasks"][0]
        command[4] = "http://" + next(d["value"] for a in task["attachments"] for d in a["details"] if d["name"] == "privateIPv4Address") + ":8000"
        eni = next(d["value"] for a in task["attachments"] for d in a["details"] if d["name"] == "networkInterfaceId")
        interface = aws("ec2", "describe-network-interfaces", "--network-interface-ids", eni)["NetworkInterfaces"][0]
        groups = aws("ec2", "describe-security-groups", "--group-ids", *[g["GroupId"] for g in interface["Groups"]])["SecurityGroups"]
        assert all(not r.get("IpRanges") and not r.get("Ipv6Ranges") for g in groups for r in g["IpPermissions"])
        save("private-network.json", [{"group": g["GroupId"], "ingress": g["IpPermissions"]} for g in groups])
        network = {"awsvpcConfiguration": {"subnets": [temporary["subnet"]], "securityGroups": [temporary["security_group"]], "assignPublicIp": "ENABLED"}}
        result = aws("ecs", "run-task", "--cluster", CLUSTER, "--launch-type", "FARGATE", "--count", "1", "--started-by", run_id,
                     "--client-token", run_id, "--task-definition", temporary["task_definition"], "--network-configuration", json.dumps(network),
                     "--overrides", json.dumps({"containerOverrides": [{"name": "synthetic", "command": command}]}))
        assert not result.get("failures") and len(result["tasks"]) == 1
        task_arn = result["tasks"][0]["taskArn"]
        metadata["task_arn"] = task_arn
        save("run.json", metadata)
        print("ERROR_TRAFFIC_TASK", task_arn, flush=True)
        stream = "synthetic/synthetic/" + task_arn.split("/")[-1]
        records, phases, metric_phases, verified = [], set(), set(), False
        started = time.monotonic()
        while time.monotonic() - started < 1000:
            task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", task_arn)["tasks"][0]
            logs = subprocess.run(AWS + ["logs", "get-log-events", "--log-group-name", "/ecs/observability-integrator", "--log-stream-name", stream,
                                  "--start-from-head", "--limit", "10000"], capture_output=True, text=True)
            if logs.returncode == 0:
                records = []
                for event in json.loads(logs.stdout).get("events", []):
                    try:
                        records.append(json.loads(event["message"]))
                    except json.JSONDecodeError:
                        pass
                for record in records:
                    if record.get("event") == "chaos.phase.started" and record["phase"] not in phases:
                        phases.add(record["phase"])
                        print("ERROR_PHASE", record["phase"], record["utc"], flush=True)
                    if record.get("event") == "chaos.phase.finished" and record["phase"] in ["injection", "recovery"] and record["phase"] not in metric_phases:
                        metric_phases.add(record["phase"])
                        save("error-counter-after-" + record["phase"] + ".json", shared.metric('{"chaos.injected.errors","@resource.service.name"="data-service"}'))
                if "injection" in phases and not verified:
                    marker = next(r for r in records if r.get("event") == "chaos.phase.started" and r["phase"] == "injection")
                    since = int(datetime.fromisoformat(marker["utc"]).timestamp() * 1000)
                    events = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel", "--log-stream-names", "data-service",
                                 "--start-time", str(since), "--filter-pattern", '"chaos.error.injected"')["events"]
                    if events:
                        verified = True
                        metadata["fault_started_utc"] = datetime.fromtimestamp(min(e["timestamp"] for e in events) / 1000, timezone.utc).isoformat()
                        metadata["verification_observed_utc"] = utc()
                        save("run.json", metadata)
                        print("ERROR_INJECTION_CONFIRMED", metadata["fault_started_utc"], flush=True)
                    elif time.time() * 1000 - since > 65000:
                        raise RuntimeError("No injected errors confirmed; stop traffic")
            if task["lastStatus"] == "STOPPED":
                assert all(c.get("exitCode") == 0 for c in task["containers"])
                if any(r.get("event") == "chaos.summary" for r in records):
                    break
            time.sleep(20)
        else:
            raise RuntimeError("Traffic exceeded its bounded window")
        assert verified
        samples = [r for r in records if "phase" in r and "duration_ms" in r]
        summary = next(r for r in records if r.get("event") == "chaos.summary")
        save("summary.json", summary)
        save("setup.json", next(r for r in records if r.get("event") == "chaos.setup.complete"))
        save("phase-events.json", [r for r in records if r.get("event", "").startswith("chaos.phase.")])
        (output / "samples.jsonl").write_text("".join(json.dumps(s) + "\n" for s in samples), encoding="utf-8")
        print("ERROR_PHASE_RESULTS", json.dumps(summary["phases"]), flush=True)
        assert all(s["status"] in ([200, 503] if s["phase"] == "injection" else [200]) for s in samples), "Unexplained HTTP outcomes"
        since = int(datetime.fromisoformat(summary["phases"]["injection"]["started_utc"]).timestamp() * 1000)
        data_logs = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel", "--log-stream-names", "data-service",
                        "--start-time", str(since), "--filter-pattern", '"chaos.error.injected"')["events"]
        affected_ids = {json.loads(e["message"])["traceId"] for e in data_logs}
        assert affected_ids
        selected = []
        for phase in ["baseline", "injection", "recovery"]:
            rows = [s for s in samples if s["phase"] == phase and s["status"] == 200 and s["trace_id"] not in affected_ids]
            selected += [rows[0], rows[len(rows) // 2], rows[-1]]
        errors = [s for s in samples if s["trace_id"] in affected_ids]
        selected += [errors[0], errors[len(errors) // 2], errors[-1]]
        traces = []
        for sample in selected:
            trace_id = "1-" + sample["trace_id"][:8] + "-" + sample["trace_id"][8:]
            response = aws("xray", "batch-get-traces", "--trace-ids", trace_id)
            spans = []
            for trace in response.get("Traces", []):
                for segment in trace["Segments"]:
                    spans += shared.flatten(json.loads(segment["Document"]))
            traces.append({"phase": sample["phase"], "http_status": sample["status"], "injected_fault": sample["trace_id"] in affected_ids, "trace_id": trace_id, "spans": spans})
        save("xray-traces.json", traces)
        for trace in traces:
            assert {"service-a", "service-b", "data-service"} <= {s["service"] for s in trace["spans"]}
            faults = [s for s in trace["spans"] if s["name"] == "chaos.error" and s["service"] == "data-service"]
            assert bool(faults) == trace["injected_fault"]
            assert any(s["db_system"] == "postgresql" for s in trace["spans"]) == (trace["http_status"] == 200)
        failed_ids = affected_ids
        since = int(datetime.fromisoformat(summary["phases"]["injection"]["started_utc"]).timestamp() * 1000)
        logs = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel", "--start-time", str(since))["events"]
        correlated = []
        for event in logs:
            record = json.loads(event["message"])
            if record.get("traceId") in failed_ids:
                correlated.append({"service": event["logStreamName"], "timestamp_ms": event["timestamp"], "event": record.get("body"),
                                   "trace_id": record.get("traceId"), "span_id": record.get("spanId")})
        save("correlated-failure-logs.json", correlated)
        eligible_metric = shared.metric('{"chaos.error.eligible.requests","@resource.service.name"="data-service"}')
        error_metric = shared.metric('{"chaos.injected.errors","@resource.service.name"="data-service"}')
        save("eligible-counter.json", eligible_metric)
        save("injected-error-counter.json", error_metric)
        eligible_count = sum(float(r["value"][1]) for r in eligible_metric["result"]["data"]["result"])
        error_count = sum(float(r["value"][1]) for r in error_metric["result"]["data"]["result"])
        assert error_count == len(data_logs) and error_count == (int(eligible_count) + 9) // 10
        save("server-error-slo.json", {"eligible_physical_attempts": eligible_count, "injected_errors": error_count,
             "server_error_rate": error_count / eligible_count, "unique_client_requests_affected": len(affected_ids),
             "client_final_errors": sum(s["status"] != 200 for s in samples), "target": 0.995,
             "server_window_budget_consumption_percent": error_count / (eligible_count * .005) * 100,
             "scope": "Data-service marked attempts including proxy retries; distinct from the end-to-end client SLO"})
        save("memory-metrics.json", shared.metric('{"credit.process.memory"}'))
        alarms = [a for a in aws("cloudwatch", "describe-alarms").get("MetricAlarms", []) if "observability-integrator" in json.dumps(a)]
        save("alerts.json", {"observed_utc": utc(), "matching_alarms": [{"name": a["AlarmName"], "state": a["StateValue"], "updated": a.get("StateUpdatedTimestamp")} for a in alarms],
             "mttd_alert_seconds": None, "limitation": "No independently verified correlated alert; operational verification is not alert MTTD"})
        metadata["completed_utc"] = utc()
        save("run.json", metadata)
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)
        save("experiment-error.json", {"utc": utc(), "error": failure})
        print("ERROR_EXPERIMENT_FAILED", failure, flush=True)
    finally:
        if attempted:
            try:
                running = aws("ecs", "list-tasks", "--cluster", CLUSTER, "--started-by", run_id)["taskArns"]
                for arn in running:
                    aws("ecs", "stop-task", "--cluster", CLUSTER, "--task", arn, "--reason", "controlled-error-experiment-cleanup")
                if running:
                    result = subprocess.run(AWS + ["ecs", "wait", "tasks-stopped", "--cluster", CLUSTER, "--tasks", *running], capture_output=True, text=True)
                    assert result.returncode == 0
                plan = ".terraform/" + run_id + "-cleanup.tfplan"
                tf("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=false", "-var=data_error_expires_at=0", "-out=" + plan)
                save("cleanup-plan-summary.json", review(plan, cleanup=True))
                print("DISARMING_ERROR_EXPERIMENT", flush=True)
                tf("apply", "-input=false", "-no-color", plan)
                health = shared.wait_healthy()
                collector_errors = []
                for service in health:
                    task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", service["task"])["tasks"][0]
                    definition = aws("ecs", "describe-task-definition", "--task-definition", task["taskDefinitionArn"])["taskDefinition"]
                    app = next(c for c in definition["containerDefinitions"] if c["name"] == service["service"])
                    assert not any("CHAOS_" in e["name"] for e in app.get("environment", []))
                    collector = next(c for c in task["containers"] if c["name"] == "collector")
                    assert collector["lastStatus"] == "RUNNING" and collector["image"].endswith("/collector:traces-v2")
                    stream = service["service"] + "-collector/collector/" + task["taskArn"].split("/")[-1]
                    records = aws("logs", "get-log-events", "--log-group-name", "/ecs/observability-integrator", "--log-stream-name", stream, "--limit", "10000")["events"]
                    collector_errors.append({"service": service["service"], "export_errors": sum(any(term in e["message"] for term in ["Exporting failed", "AccessDenied", "StatusCode: 400"]) for e in records)})
                save("final-services.json", health)
                save("final-collector-errors.json", collector_errors)
                assert "No changes." in tf("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=false", "-var=data_error_expires_at=0", "-detailed-exitcode")
                assert not aws("ec2", "describe-security-groups", "--filters", "Name=group-name,Values=observability-integrator-synthetic-test")["SecurityGroups"]
                if temporary:
                    aws("ecs", "delete-task-definitions", "--task-definitions", temporary["task_definition"])
                if task_arn and (output / "samples.jsonl").exists():
                    aws("logs", "delete-log-stream", "--log-group-name", "/ecs/observability-integrator", "--log-stream-name", "synthetic/synthetic/" + task_arn.split("/")[-1])
                save("cleanup.json", {"utc": utc(), "data_error_expires_at": 0, "temporary_groups": 0, "services_healthy": 3,
                     "terraform": "No changes", "data_writes": 0, "data_service_image": TAG})
                print("ERROR_EXPERIMENT_CLEANUP_VERIFIED", str(output.relative_to(ROOT)), flush=True)
            except BaseException as error:
                save("cleanup-error.json", {"utc": utc(), "error": str(error), "deadline_epoch": deadline})
                raise RuntimeError("Cleanup failed; stop and inspect evidence. No unrelated remediation attempted") from error
    if failure:
        raise RuntimeError("Experiment incomplete; cleanup performed. See saved evidence")


if __name__ == "__main__":
    main()
