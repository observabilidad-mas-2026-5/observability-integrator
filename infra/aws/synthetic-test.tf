variable "enable_synthetic_test" {
  type        = bool
  default     = false
  description = "Prepare a one-shot private synthetic client; never launches a task."
}

resource "aws_security_group" "synthetic_test" {
  count       = var.enable_synthetic_test ? 1 : 0
  name        = "${var.name}-synthetic-test"
  description = "Temporary synthetic client with no ingress"
  vpc_id      = aws_vpc.lab.id
}

resource "aws_vpc_security_group_egress_rule" "synthetic_api" {
  count                        = var.enable_synthetic_test ? 1 : 0
  security_group_id            = aws_security_group.synthetic_test[0].id
  referenced_security_group_id = aws_security_group.service["service-a"].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "synthetic_https" {
  count             = var.enable_synthetic_test ? 1 : 0
  security_group_id = aws_security_group.synthetic_test[0].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "ECR API, ECR layers in S3 and CloudWatch Logs via HTTPS"
}

resource "aws_vpc_security_group_ingress_rule" "synthetic_api" {
  count                        = var.enable_synthetic_test ? 1 : 0
  security_group_id            = aws_security_group.service["service-a"].id
  referenced_security_group_id = aws_security_group.synthetic_test[0].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

locals {
  synthetic_request = <<-PYTHON
    import datetime, ipaddress, json, os, secrets, time, urllib.request
    address = ipaddress.ip_address(os.environ["SERVICE_A_PRIVATE_IP"])
    if address.version != 4 or not address.is_private:
        raise ValueError("Service A must use a private IPv4 address")
    trace_id = format(int(time.time()), "08x") + secrets.token_hex(12)
    parent_id = secrets.token_hex(8)
    traceparent = "00-" + trace_id + "-" + parent_id + "-01"
    xray_id = "1-" + trace_id[:8] + "-" + trace_id[8:]
    print(json.dumps({"event": "synthetic.request", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "trace_id": trace_id, "xray_trace_id": xray_id, "traceparent": traceparent}), flush=True)
    payload = {"customer_name": "PRUEBA SINTETICA INTEGRADOR", "document_number": "LAB-TRACE-001", "requested_amount": 1000}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, target):
            return None
    request = urllib.request.Request("http://" + str(address) + ":8000/credit-applications", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "traceparent": traceparent}, method="POST")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
        result = json.load(response)
        print(json.dumps({"event": "synthetic.response", "http_status": response.status, "application_id": result.get("application_id"), "status": result.get("status"), "trace_id": trace_id}), flush=True)
        if response.status != 201 or not result.get("application_id") or result.get("status") != "PENDING":
            raise RuntimeError("Expected HTTP 201 and a persisted PENDING application")
    request_read = urllib.request.Request("http://" + str(address) + ":8000/credit-applications/" + result["application_id"], method="GET")
    with urllib.request.build_opener(NoRedirect).open(request_read, timeout=25) as read_response:
        persisted = json.load(read_response)
        if read_response.status != 200 or persisted["application_id"] != result["application_id"] or persisted["status"] != "PENDING":
            raise RuntimeError("Persistence verification failed")
        print(json.dumps({"event": "synthetic.persistence.confirmed", "http_status": read_response.status, "application_id": persisted["application_id"]}), flush=True)
  PYTHON
}

resource "aws_ecs_task_definition" "synthetic_test" {
  count                    = var.enable_synthetic_test ? 1 : 0
  family                   = "${var.name}-synthetic-test"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution["service-a"].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name                   = "synthetic"
    image                  = "${aws_ecr_repository.images["api"].repository_url}:initial"
    essential              = true
    readonlyRootFilesystem = true
    command                = ["python", "-c", local.synthetic_request]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.runtime.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "synthetic"
      }
    }
  }])
}

output "synthetic_test" {
  value = var.enable_synthetic_test ? {
    task_definition = aws_ecs_task_definition.synthetic_test[0].arn
    security_group  = aws_security_group.synthetic_test[0].id
    subnet          = aws_subnet.tasks.id
  } : null
}
