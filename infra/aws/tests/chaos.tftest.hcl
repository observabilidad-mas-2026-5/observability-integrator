mock_provider "aws" {
  override_during = plan

  mock_data "aws_availability_zones" {
    defaults = {
      names = ["us-east-2a", "us-east-2b"]
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      repository_url = "467866783326.dkr.ecr.us-east-2.amazonaws.com/observability-integrator/mock"
      arn            = "arn:aws:ecr:us-east-2:467866783326:repository/observability-integrator/mock"
    }
  }

  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{
        secret_arn = "arn:aws:secretsmanager:us-east-2:467866783326:secret:mock-only"
      }]
    }
  }
}

variables {
  deploy_services     = true
  image_tag           = "initial"
  collector_image_tag = "traces-v2"
}

run "defaults_preserve_containers" {
  command = plan

  assert {
    condition     = jsonencode(local.application_containers) == jsonencode(local.containers)
    error_message = "Default overrides must preserve every current container definition."
  }
}

run "latency_changes_only_a_and_b" {
  command = plan
  variables {
    api_image_tags   = { service-a = "chaos-latency-v1", service-b = "chaos-latency-v1" }
    chaos_expires_at = 1800000000
  }

  assert {
    condition     = jsonencode(local.application_containers["data-service"]) == jsonencode(local.containers["data-service"])
    error_message = "data-service must remain unchanged."
  }
  assert {
    condition = alltrue([
      for service in ["service-a", "service-b"] :
      endswith(local.application_containers[service][0].image, ":chaos-latency-v1") &&
      contains(local.application_containers[service][0].environment, { name = "CHAOS_ENABLED", value = "true" }) &&
      contains(local.application_containers[service][0].environment, { name = "CHAOS_EXPIRES_AT", value = "1800000000" }) &&
      jsonencode(local.application_containers[service][1]) == jsonencode(local.containers[service][1]) &&
      endswith(local.application_containers[service][1].image, ":traces-v2")
    ])
    error_message = "Only the A/B applications may change image and receive chaos variables; Collectors must not change."
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.service : service.desired_count == 1]) && !aws_db_instance.lab.publicly_accessible
    error_message = "Services must remain active and RDS private."
  }
}

run "disable_chaos_without_reverting_image" {
  command = plan
  variables {
    api_image_tags   = { service-a = "chaos-latency-v1", service-b = "chaos-latency-v1" }
    chaos_expires_at = 0
  }
  assert {
    condition = alltrue([
      for service in ["service-a", "service-b"] :
      endswith(local.application_containers[service][0].image, ":chaos-latency-v1") &&
      jsonencode(local.application_containers[service][0].environment) == jsonencode(local.containers[service][0].environment)
    ])
    error_message = "Disarming must remove chaos variables without changing the selected API tag."
  }
}

run "reject_mutable_tag" {
  command = plan
  variables {
    api_image_tags = { service-a = "latest" }
  }
  expect_failures = [var.api_image_tags]
}

run "data_errors_do_not_modify_a_or_b" {
  command = plan
  variables {
    api_image_tags            = { service-a = "chaos-latency-v1", service-b = "chaos-latency-v1", data-service = "chaos-errors-v1" }
    data_error_expires_at     = 1800000000
    data_error_application_id = "c32d2d6c-b73b-4a32-ab55-bbb23da6c616"
  }
  assert {
    condition = alltrue([for service in ["service-a", "service-b"] :
      endswith(local.application_containers[service][0].image, ":chaos-latency-v1") &&
      jsonencode(local.application_containers[service][0].environment) == jsonencode(local.containers[service][0].environment)
    ])
    error_message = "Error injection must not add variables or change the A/B images."
  }
  assert {
    condition = (endswith(local.application_containers["data-service"][0].image, ":chaos-errors-v1") &&
      contains(local.application_containers["data-service"][0].environment, { name = "DATA_CHAOS_ENABLED", value = "true" }) &&
    jsonencode(local.application_containers["data-service"][1]) == jsonencode(local.containers["data-service"][1]))
    error_message = "Only the data application may receive the error gate; its Collector must not change."
  }
}
