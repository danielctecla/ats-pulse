variable "aws_region" {
  description = "AWS region where everything is deployed."
  type        = string
  default     = "us-east-1"
}

variable "lambda_memory_mb" {
  description = "Memory in MB for the Lambda function."
  type        = number
  default     = 256
}

variable "lambda_runtime" {
  description = "Lambda Python runtime identifier."
  type        = string
  default     = "python3.15"
}

variable "lambda_timeout_seconds" {
  description = "Maximum run time of one invocation (all sources), in seconds."
  type        = number
  default     = 180
}

variable "log_retention_days" {
  description = "Days to keep the Lambda logs in CloudWatch."
  type        = number
  default     = 14
}

variable "notification_email" {
  description = "Address that receives the digest and alerts. Also the SES sender identity. Provide via TF_VAR_notification_email; never commit it."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.notification_email))
    error_message = "notification_email must be a valid email address."
  }
}

variable "project_name" {
  description = "Prefix for resource names. Also tagged as Project on every resource."
  type        = string
  default     = "ats-pulse"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,40}$", var.project_name))
    error_message = "project_name may only contain lowercase letters, numbers and hyphens (max 40)."
  }
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression. Use cron() so schedule_timezone applies (rate() ignores it)."
  type        = string
  default     = "cron(0 0/3 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone for schedule_expression."
  type        = string
  default     = "America/Mexico_City"
}

variable "tags" {
  description = "Extra tags for every resource, on top of Project and ManagedBy."
  type        = map(string)
  default     = {}
}
