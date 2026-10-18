variable "api_image_tags" {
  type        = map(string)
  default     = {}
  description = "Optional immutable API tags by service; omitted services inherit image_tag."
  validation {
    condition = alltrue([
      for service, tag in var.api_image_tags :
      contains(["service-a", "service-b", "data-service"], service) &&
      can(regex("^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$", tag)) && tag != "latest"
    ])
    error_message = "Use known integrator service names and explicit immutable release tags."
  }
}

variable "chaos_expires_at" {
  type        = number
  default     = 0
  description = "UTC epoch deadline enabling request-scoped latency on A/B; zero omits all chaos environment variables. Application enforces expiry and the 30-minute bound."
  validation {
    condition     = var.chaos_expires_at >= 0 && floor(var.chaos_expires_at) == var.chaos_expires_at
    error_message = "Use a nonnegative integer UTC epoch, or zero to keep chaos disabled."
  }
}

variable "data_error_expires_at" {
  type        = number
  default     = 0
  description = "UTC epoch enabling synthetic read failures only in data-service; zero disarms."
  validation {
    condition = var.data_error_expires_at >= 0 && floor(var.data_error_expires_at) == var.data_error_expires_at && (
      var.data_error_expires_at == 0 || can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.data_error_application_id))
    )
    error_message = "Use a nonnegative epoch and a specific synthetic UUID when enabling failures."
  }
}

variable "data_error_application_id" {
  type        = string
  default     = ""
  description = "Allowlisted synthetic record; no other application ID is eligible."
}

locals {
  application_containers = {
    for service, containers in local.containers : service => [
      for container in containers : container.name != service ? container : merge(container, {
        image = "${aws_ecr_repository.images["api"].repository_url}:${lookup(var.api_image_tags, service, var.image_tag)}"
        environment = concat(container.environment, var.chaos_expires_at > 0 && contains(["service-a", "service-b"], service) ? [
          { name = "CHAOS_ENABLED", value = "true" },
          { name = "CHAOS_EXPIRES_AT", value = tostring(var.chaos_expires_at) }
          ] : [], var.data_error_expires_at > 0 && service == "data-service" ? [
          { name = "DATA_CHAOS_ENABLED", value = "true" },
          { name = "DATA_CHAOS_EXPIRES_AT", value = tostring(var.data_error_expires_at) },
          { name = "DATA_CHAOS_APPLICATION_ID", value = var.data_error_application_id }
        ] : [])
      })
    ]
  }
}
