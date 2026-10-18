import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AWS = ["aws", "--profile", "observability-integrator", "--region", "us-east-2"]
CLUSTER = "observability-integrator"
SERVICES = ["service-a", "service-b", "data-service"]
FLAGS = ["-var=deploy_services=true", "-var=image_tag=initial", "-var=collector_image_tag=traces-v2",
         '-var=api_image_tags={"service-a":"chaos-latency-v1","service-b":"chaos-latency-v1"}']
TEMP = {"aws_security_group.synthetic_test[0]", "aws_ecs_task_definition.synthetic_test[0]",
        "aws_vpc_security_group_ingress_rule.synthetic_api[0]", "aws_vpc_security_group_egress_rule.synthetic_api[0]",
        "aws_vpc_security_group_egress_rule.synthetic_https[0]"}
APPLICATIONS = {f'aws_ecs_{kind}.service["{service}"]' for kind in ["service", "task_definition"] for service in SERVICES[:2]}


def utc():
    return datetime.now(timezone.utc).isoformat()


def aws(*args):
    result = subprocess.run(AWS + list(args) + ["--output", "json"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Personal AWS command failed: " + " ".join(args[:2]) + "; no fallback profile attempted")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def credentials():
    return aws("configure", "export-credentials", "--format", "process")


def terraform(*args):
    secret = credentials()
    env = os.environ.copy()
    for name in ["AWS_PROFILE", "AWS_DEFAULT_PROFILE"]:
        env.pop(name, None)
    env.update(AWS_ACCESS_KEY_ID=secret["AccessKeyId"], AWS_SECRET_ACCESS_KEY=secret["SecretAccessKey"],
               AWS_SESSION_TOKEN=secret["SessionToken"], AWS_REGION="us-east-2", AWS_DEFAULT_REGION="us-east-2")
    result = subprocess.run(["terraform", "-chdir=infra/aws"] + list(args), cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError("Terraform " + args[0] + " failed; stopped without broadening resource scope")
    return result.stdout


def normalized(container):
    value = json.loads(json.dumps(container))
    for key in ["mountPoints", "volumesFrom", "systemControls", "portMappings"]:
        if value.get(key) in [None, []]:
            value.pop(key, None)
    for port in value.get("portMappings", []):
        if port.get("hostPort") == port.get("containerPort"):
            port.pop("hostPort")
    return value


def review(path, cleanup=False):
    plan = json.loads(terraform("show", "-json", path))
    changes = [r for r in plan["resource_changes"] if r["change"]["actions"] not in [["no-op"], ["read"]]]
    addresses = {r["address"] for r in changes}
    if not addresses <= TEMP | APPLICATIONS or (not cleanup and addresses != TEMP | APPLICATIONS):
        raise RuntimeError("Unexpected resource scope: " + str(sorted(addresses)))
    for resource in changes:
        change = resource["change"]
        before, after = change.get("before") or {}, change.get("after") or {}
        if resource["address"] in TEMP:
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
            old = normalized(next(c for c in old_containers if c["name"] == container["name"]))
            new = normalized(container)
            if container["name"] == "collector":
                assert old == new and new["image"].endswith("/collector:traces-v2")
                continue
            assert old["image"] == new["image"] and new["image"].endswith("/api:chaos-latency-v1")
            old_env, new_env = old.pop("environment"), new.pop("environment")
            assert old == new
            without_chaos = lambda items: [e for e in items if not e["name"].startswith("CHAOS_")]
            assert without_chaos(old_env) == without_chaos(new_env)
            assert bool([e for e in new_env if e["name"] == "CHAOS_ENABLED" and e["value"] == "true"]) != cleanup
    summary = [{"address": r["address"], "actions": r["change"]["actions"]} for r in changes]
    print("PLAN_REVIEW", json.dumps(summary), flush=True)
    return summary


def metric(query):
    secret = credentials()
    now = datetime.now(timezone.utc)
    date, stamp = now.strftime("%Y%m%d"), now.strftime("%Y%m%dT%H%M%SZ")
    host, path = "monitoring.us-east-2.amazonaws.com", "/api/v1/query"
    query_string = "query=" + urllib.parse.quote(query, safe="-_.~")
    headers = {"host": host, "x-amz-date": stamp, "x-amz-security-token": secret["SessionToken"]}
    keys = ";".join(sorted(headers))
    canonical = "".join(k + ":" + headers[k] + "\n" for k in sorted(headers))
    request = "GET\n" + path + "\n" + query_string + "\n" + canonical + "\n" + keys + "\n" + hashlib.sha256(b"").hexdigest()
    scope = date + "/us-east-2/monitoring/aws4_request"
    message = "AWS4-HMAC-SHA256\n" + stamp + "\n" + scope + "\n" + hashlib.sha256(request.encode()).hexdigest()
    key = ("AWS4" + secret["SecretAccessKey"]).encode()
    for part in [date, "us-east-2", "monitoring", "aws4_request"]:
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = "AWS4-HMAC-SHA256 Credential=" + secret["AccessKeyId"] + "/" + scope + ", SignedHeaders=" + keys + ", Signature=" + signature
    with urllib.request.urlopen(urllib.request.Request("https://" + host + path + "?" + query_string, headers=headers), timeout=40) as response:
        return {"queried_utc": utc(), "query": query, "http_status": response.status, "result": json.load(response)}


def services():
    return aws("ecs", "describe-services", "--cluster", CLUSTER, "--services", *[CLUSTER + "-" + s for s in SERVICES])["services"]


def wait_healthy():
    result = subprocess.run(AWS + ["ecs", "wait", "services-stable", "--cluster", CLUSTER,
                            "--services", *[CLUSTER + "-" + s for s in SERVICES]], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("ECS did not stabilize; no unrelated remediation attempted")
    arns = aws("ecs", "list-tasks", "--cluster", CLUSTER)["taskArns"]
    tasks = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", *arns)["tasks"]
    result = []
    for name in SERVICES:
        task = next(t for t in tasks if t["group"] == "service:" + CLUSTER + "-" + name)
        app = next(c for c in task["containers"] if c["name"] == name)
        assert task["lastStatus"] == "RUNNING" and app.get("healthStatus") == "HEALTHY"
        result.append({"service": name, "task": task["taskArn"], "health": app["healthStatus"], "image": app["image"]})
    assert all(s["desiredCount"] == s["runningCount"] == 1 and s["pendingCount"] == 0 for s in services())
    return result


def flatten(document, parent=None, service=None, trace_id=None):
    metadata = document.get("metadata", {}).get("default", {})
    service = metadata.get("otel.resource.service.name", service)
    trace_id = document.get("trace_id", trace_id)
    rows = [{"name": document.get("name"), "id": document.get("id"), "parent_id": document.get("parent_id", parent),
             "service": service, "trace_id": trace_id, "start_time": document.get("start_time"),
             "end_time": document.get("end_time"), "db_system": metadata.get("db.system.name"),
             "http_status": document.get("http", {}).get("response", {}).get("status"),
             "db_operation": metadata.get("db.operation.name"), "error": document.get("error"), "fault": document.get("fault")}]
    for child in document.get("subsegments", []):
        rows += flatten(child, document.get("id"), service, trace_id)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        parser.error("Explicit --execute authorization is required")
    assert aws("sts", "get-caller-identity")["Account"] == "467866783326"
    assert all(s["desiredCount"] == s["runningCount"] == 1 for s in services())
    run_id = "chaos-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "docs/evidence/integrator/aws/chaos" / run_id
    output.mkdir(parents=True, exist_ok=False)
    save = lambda name, value: (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    deadline = int(time.time()) + 1700
    metadata = {"run_id": run_id, "started_utc": utc(), "deadline_epoch": deadline, "region": "us-east-2"}
    source = (ROOT / "scripts/chaos_latency.py").read_text(encoding="utf-8")
    compile(source, "chaos_latency.py", "exec")
    encoded = base64.b64encode(zlib.compress(source.encode())).decode()
    bootstrap = "import base64,zlib;exec(zlib.decompress(base64.b64decode(" + repr(encoded) + ")))"
    command = ["python", "-c", bootstrap, "--base-url", "http://10.52.0.1:8000", "--output-dir", "-",
               "--environment", "aws", "--phase-seconds", "180", "--rps", "3"]
    assert len(json.dumps({"containerOverrides": [{"name": "synthetic", "command": command}]})) < 8192
    mutation_attempted = False
    task_arn = None
    temp = None
    experiment_error = None
    try:
        plan = ".terraform/" + run_id + "-arm.tfplan"
        terraform("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=true",
                  "-var=chaos_expires_at=" + str(deadline), "-out=" + plan)
        save("activation-plan-summary.json", review(plan))
        mutation_attempted = True
        print("ACTIVATING_EXPERIMENT", run_id, "deadline", deadline, flush=True)
        terraform("apply", "-input=false", "-no-color", plan)
        save("armed-services.json", wait_healthy())
        assert deadline - time.time() > 720, "Not enough time before expiry; abort without traffic"
        temp = json.loads(terraform("output", "-json", "synthetic_test"))
        a_arn = aws("ecs", "list-tasks", "--cluster", CLUSTER, "--service-name", CLUSTER + "-service-a")["taskArns"][0]
        a_task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", a_arn)["tasks"][0]
        ip = next(d["value"] for a in a_task["attachments"] for d in a["details"] if d["name"] == "privateIPv4Address")
        eni = next(d["value"] for a in a_task["attachments"] for d in a["details"] if d["name"] == "networkInterfaceId")
        interface = aws("ec2", "describe-network-interfaces", "--network-interface-ids", eni)["NetworkInterfaces"][0]
        groups_a = aws("ec2", "describe-security-groups", "--group-ids", *[g["GroupId"] for g in interface["Groups"]])["SecurityGroups"]
        assert all(not rule.get("IpRanges") and not rule.get("Ipv6Ranges") for group in groups_a for rule in group["IpPermissions"]), "Public ingress detected; abort"
        client_group = aws("ec2", "describe-security-groups", "--group-ids", temp["security_group"])["SecurityGroups"][0]
        assert not client_group["IpPermissions"]
        save("private-network.json", {"service_a_ingress": [g["IpPermissions"] for g in groups_a], "client_ingress": [], "client_egress": client_group["IpPermissionsEgress"]})
        command[4] = "http://" + ip + ":8000"
        network = {"awsvpcConfiguration": {"subnets": [temp["subnet"]], "securityGroups": [temp["security_group"]], "assignPublicIp": "ENABLED"}}
        overrides = {"containerOverrides": [{"name": "synthetic", "command": command}]}
        assert len(json.dumps(overrides)) < 8192
        result = aws("ecs", "run-task", "--cluster", CLUSTER, "--launch-type", "FARGATE", "--count", "1",
                     "--started-by", run_id, "--client-token", run_id, "--task-definition", temp["task_definition"],
                     "--network-configuration", json.dumps(network), "--overrides", json.dumps(overrides))
        assert not result.get("failures") and len(result["tasks"]) == 1
        task_arn = result["tasks"][0]["taskArn"]
        metadata.update(task_arn=task_arn, task_definition=temp["task_definition"], temporary_group=temp["security_group"])
        save("run.json", metadata)
        print("TRAFFIC_TASK", task_arn, flush=True)
        stream = "synthetic/synthetic/" + task_arn.split("/")[-1]
        records = []
        seen_phases = set()
        metric_phases = set()
        verified = False
        started = time.monotonic()
        while time.monotonic() - started < 1000:
            task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", task_arn)["tasks"][0]
            logs = subprocess.run(AWS + ["logs", "get-log-events", "--log-group-name", "/ecs/observability-integrator",
                                  "--log-stream-name", stream, "--start-from-head", "--limit", "10000"], capture_output=True, text=True)
            if logs.returncode == 0:
                records = []
                for event in json.loads(logs.stdout).get("events", []):
                    try:
                        records.append(json.loads(event["message"]))
                    except json.JSONDecodeError:
                        pass
                for record in records:
                    if record.get("event") == "chaos.phase.started" and record["phase"] not in seen_phases:
                        seen_phases.add(record["phase"])
                        print("PHASE", record["phase"], record["utc"], flush=True)
                    if record.get("event") == "chaos.phase.finished" and record["phase"] in ["injection", "recovery"] and record["phase"] not in metric_phases:
                        metric_phases.add(record["phase"])
                        save("cloudwatch-counter-after-" + record["phase"] + ".json", metric('{"chaos.injected.requests","@resource.service.name"="service-b"}'))
                if "injection" in seen_phases and not verified:
                    marker = next(r for r in records if r.get("event") == "chaos.phase.started" and r["phase"] == "injection")
                    start_ms = int(datetime.fromisoformat(marker["utc"]).timestamp() * 1000)
                    events = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel",
                                 "--log-stream-names", "service-b", "--start-time", str(start_ms),
                                 "--filter-pattern", '"chaos.latency.started"')["events"]
                    if events:
                        verified = True
                        metadata["injection_verified_observed_utc"] = utc()
                        metadata["fault_started_utc"] = datetime.fromtimestamp(min(e["timestamp"] for e in events) / 1000, timezone.utc).isoformat()
                        save("run.json", metadata)
                        print("INJECTION_CONFIRMED_IN_B", metadata["fault_started_utc"], flush=True)
                    elif time.time() * 1000 - start_ms > 65000:
                        raise RuntimeError("Injection not confirmed within 65 seconds; stopping traffic")
            if task["lastStatus"] == "STOPPED":
                assert all(c.get("exitCode") == 0 for c in task["containers"]), "Traffic task failed; POST will not be retried"
                if any(r.get("event") == "chaos.summary" for r in records):
                    break
            time.sleep(20)
        else:
            raise RuntimeError("Traffic task exceeded its bounded window")
        assert verified, "No real injection was confirmed"
        samples = [r for r in records if r.get("phase") in ["baseline", "injection", "recovery"] and "duration_ms" in r]
        summary = next(r for r in records if r.get("event") == "chaos.summary")
        setup = next(r for r in records if r.get("event") == "chaos.setup.complete")
        assert setup["status"] == 201
        save("setup.json", setup)
        save("summary.json", summary)
        (output / "samples.jsonl").write_text("".join(json.dumps(r) + "\n" for r in samples), encoding="utf-8")
        save("client-phase-events.json", [r for r in records if r.get("event", "").startswith("chaos.phase.")])
        baseline = summary["phases"]["baseline"]
        recovery = summary["phases"]["recovery"]
        save("recovery-comparison.json", {"baseline_p99_ms": baseline["p99_ms"], "recovery_p99_ms": recovery["p99_ms"],
             "tolerance_ms": max(20, 0.2 * baseline["p99_ms"]), "within_descriptive_tolerance": recovery["p99_ms"] <= baseline["p99_ms"] + max(20, 0.2 * baseline["p99_ms"]),
             "baseline_error_rate": baseline["error_rate"], "recovery_error_rate": recovery["error_rate"]})
        print("PHASE_SUMMARY", json.dumps(summary["phases"]), flush=True)
        save("cloudwatch-injection-counter.json", metric('{"chaos.injected.requests","@resource.service.name"="service-b"}'))
        save("cloudwatch-memory.json", metric('{"credit.process.memory"}'))
        selected = [setup]
        for phase in ["baseline", "injection", "recovery"]:
            phase_samples = [s for s in samples if s["phase"] == phase]
            selected += [phase_samples[0], phase_samples[len(phase_samples) // 2], phase_samples[-1]]
        trace_rows = []
        for sample in selected:
            trace_id = "1-" + sample["trace_id"][:8] + "-" + sample["trace_id"][8:]
            result = aws("xray", "batch-get-traces", "--trace-ids", trace_id)
            rows = []
            for trace in result.get("Traces", []):
                for segment in trace["Segments"]:
                    rows += flatten(json.loads(segment["Document"]))
            trace_rows.append({"phase": sample.get("phase", "setup"), "trace_id": trace_id, "spans": rows})
        save("xray-selected-traces.json", trace_rows)
        injection = [t for t in trace_rows if t["phase"] == "injection"]
        assert all(any(s["name"] == "chaos.latency" and s["service"] == "service-b" and s["end_time"] - s["start_time"] >= 0.19 for s in t["spans"]) for t in injection), "Injection spans not verified"
        assert all(not any(s["name"] == "chaos.latency" for s in t["spans"]) for t in trace_rows if t["phase"] in ["baseline", "recovery"])
        assert all({"service-a", "service-b", "data-service"} <= {s["service"] for s in t["spans"]} and any(s["db_system"] == "postgresql" for s in t["spans"]) for t in trace_rows), "Incomplete representative end-to-end trace"
        start_ms = int(datetime.fromisoformat(summary["phases"]["baseline"]["started_utc"]).timestamp() * 1000)
        events = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel",
                     "--log-stream-names", "service-b", "--start-time", str(start_ms))["events"]
        safe_logs = []
        for event in events:
            record = json.loads(event["message"])
            if record.get("body") not in ["chaos.latency.started", "chaos.latency.injected"]:
                continue
            safe_logs.append({"timestamp_ms": event["timestamp"], "event": record.get("body"), "trace_id": record.get("traceId"), "span_id": record.get("spanId")})
        save("injection-logs.json", safe_logs)
        correlated = aws("logs", "filter-log-events", "--log-group-name", "/ecs/observability-integrator/otel", "--filter-pattern", '"' + setup["trace_id"] + '"')["events"]
        save("setup-correlated-logs.json", [{"service": e["logStreamName"], "timestamp_ms": e["timestamp"],
             "event": json.loads(e["message"]).get("body"), "trace_id": json.loads(e["message"]).get("traceId"),
             "span_id": json.loads(e["message"]).get("spanId")} for e in correlated])
        alarms = aws("cloudwatch", "describe-alarms").get("MetricAlarms", [])
        relevant = [a for a in alarms if "observability-integrator" in json.dumps(a)]
        save("alert-observation.json", {"observed_utc": utc(), "matching_alarm_count": len(relevant),
             "alarms": [{"name": a["AlarmName"], "state": a["StateValue"], "state_updated": a.get("StateUpdatedTimestamp")} for a in relevant],
             "mttd_alert_seconds": None, "reason": "No independently verified alert notification correlated with this fault; operational verification is not alert MTTD"})
        metadata["completed_utc"] = utc()
        metadata["injection_verified"] = True
        save("run.json", metadata)
    except BaseException as error:
        experiment_error = type(error).__name__ + ": " + str(error)
        save("experiment-error.json", {"utc": utc(), "error": experiment_error})
        print("EXPERIMENT_ERROR", experiment_error, flush=True)
    finally:
        if mutation_attempted:
            try:
                running = aws("ecs", "list-tasks", "--cluster", CLUSTER, "--started-by", run_id)["taskArns"]
                for arn in running:
                    aws("ecs", "stop-task", "--cluster", CLUSTER, "--task", arn, "--reason", "bounded-chaos-experiment-cleanup")
                if running:
                    result = subprocess.run(AWS + ["ecs", "wait", "tasks-stopped", "--cluster", CLUSTER, "--tasks", *running], capture_output=True, text=True)
                    assert result.returncode == 0
                plan = ".terraform/" + run_id + "-cleanup.tfplan"
                terraform("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=false", "-var=chaos_expires_at=0", "-out=" + plan)
                save("cleanup-plan-summary.json", review(plan, cleanup=True))
                print("DISARMING_AND_REMOVING_TEMPORARY_RESOURCES", flush=True)
                terraform("apply", "-input=false", "-no-color", plan)
                final_health = wait_healthy()
                collector_errors = []
                for service in final_health:
                    task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", service["task"])["tasks"][0]
                    definition = aws("ecs", "describe-task-definition", "--task-definition", task["taskDefinitionArn"])["taskDefinition"]
                    app = next(c for c in definition["containerDefinitions"] if c["name"] == service["service"])
                    assert not any(e["name"].startswith("CHAOS_") for e in app.get("environment", []))
                    collector = next(c for c in task["containers"] if c["name"] == "collector")
                    assert collector["lastStatus"] == "RUNNING" and collector["image"].endswith("/collector:traces-v2")
                    stream = service["service"] + "-collector/collector/" + task["taskArn"].split("/")[-1]
                    events = aws("logs", "get-log-events", "--log-group-name", "/ecs/observability-integrator", "--log-stream-name", stream, "--limit", "10000")["events"]
                    failures = [e for e in events if any(term in e["message"] for term in ["Exporting failed", "AccessDenied", "StatusCode: 400", "status code: 400"])]
                    collector_errors.append({"service": service["service"], "events_read": len(events), "export_errors": len(failures)})
                save("final-services.json", final_health)
                save("final-collector-errors.json", collector_errors)
                out = terraform("plan", "-input=false", "-no-color", *FLAGS, "-var=enable_synthetic_test=false", "-var=chaos_expires_at=0", "-detailed-exitcode")
                assert "No changes." in out
                groups = aws("ec2", "describe-security-groups", "--filters", "Name=group-name,Values=observability-integrator-synthetic-test")["SecurityGroups"]
                assert not groups
                a_task = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", final_health[0]["task"])["tasks"][0]
                groups_a = [d["value"] for a in a_task["attachments"] for d in a["details"] if d["name"] == "networkInterfaceId"]
                interface = aws("ec2", "describe-network-interfaces", "--network-interface-ids", *groups_a)["NetworkInterfaces"][0]
                security = aws("ec2", "describe-security-groups", "--group-ids", *[g["GroupId"] for g in interface["Groups"]])["SecurityGroups"]
                assert all(not g["IpPermissions"] for g in security)
                if temp:
                    aws("ecs", "delete-task-definitions", "--task-definitions", temp["task_definition"])
                if task_arn and (output / "samples.jsonl").exists():
                    aws("logs", "delete-log-stream", "--log-group-name", "/ecs/observability-integrator", "--log-stream-name", "synthetic/synthetic/" + task_arn.split("/")[-1])
                save("cleanup.json", {"utc": utc(), "chaos_expires_at": 0, "temporary_security_groups": 0,
                     "service_a_ingress": [], "terraform": "No changes", "services_healthy": 3,
                     "synthetic_record_retained": True, "temporary_task_definition_delete_requested": bool(temp)})
                print("CLEANUP_VERIFIED", str(output.relative_to(ROOT)), flush=True)
            except BaseException as error:
                save("cleanup-error.json", {"utc": utc(), "error": type(error).__name__ + ": " + str(error), "deadline_epoch": deadline})
                raise RuntimeError("CLEANUP FAILED: stop; inspect saved evidence and AWS. No unrelated remediation attempted") from error
    if experiment_error:
        raise RuntimeError("Experiment incomplete; cleanup performed. See evidence.")


if __name__ == "__main__":
    main()
