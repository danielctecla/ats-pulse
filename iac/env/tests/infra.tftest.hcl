# Runs against mocked providers: no AWS credentials, nothing is created.
# Computed ARNs are overridden with fixed values so assertions can compare
# against exact strings.

mock_provider "aws" {}
mock_provider "archive" {}

variables {
  notification_email = "test@example.com"
}

override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "123456789012" }
}

override_resource {
  target = aws_dynamodb_table.this
  values = { arn = "arn:aws:dynamodb:us-east-1:123456789012:table/ats-pulse" }
}

override_resource {
  target = aws_sesv2_email_identity.notification
  values = { arn = "arn:aws:ses:us-east-1:123456789012:identity/test@example.com" }
}

override_resource {
  target = aws_cloudwatch_log_group.lambda
  values = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/ats-pulse" }
}

override_resource {
  target = aws_lambda_function.this
  values = { arn = "arn:aws:lambda:us-east-1:123456789012:function:ats-pulse" }
}

override_resource {
  target = aws_iam_role.lambda
  values = { arn = "arn:aws:iam::123456789012:role/ats-pulse-lambda" }
}

override_resource {
  target = aws_iam_role.scheduler
  values = { arn = "arn:aws:iam::123456789012:role/ats-pulse-scheduler" }
}

run "lambda_policy_only_references_own_resources" {
  command = apply

  # Each statement flattened to "actions|resources"; the set must match exactly,
  # so any extra action, resource, wildcard or statement fails the test.
  assert {
    condition = toset([
      for s in jsondecode(aws_iam_role_policy.lambda.policy).Statement :
      "${s.Effect}|${join(",", sort(s.Action))}|${join(",", s.Resource)}"
      ]) == toset([
      "Allow|dynamodb:BatchGetItem,dynamodb:GetItem,dynamodb:PutItem,dynamodb:UpdateItem|arn:aws:dynamodb:us-east-1:123456789012:table/ats-pulse",
      "Allow|ses:SendEmail|arn:aws:ses:us-east-1:123456789012:identity/test@example.com",
      "Allow|logs:CreateLogStream,logs:PutLogEvents|arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/ats-pulse:*",
    ])
    error_message = "Lambda policy must only grant table access on its own table, ses:SendEmail on the identity, and logs on its own log group."
  }

  assert {
    condition     = jsondecode(aws_iam_role.lambda.assume_role_policy).Statement[0].Principal.Service == "lambda.amazonaws.com"
    error_message = "Lambda role must only be assumable by the Lambda service."
  }
}

run "scheduler_can_only_invoke_this_lambda" {
  command = apply

  assert {
    condition = toset([
      for s in jsondecode(aws_iam_role_policy.scheduler.policy).Statement :
      "${s.Effect}|${join(",", sort(s.Action))}|${join(",", s.Resource)}"
    ]) == toset(["Allow|lambda:InvokeFunction|arn:aws:lambda:us-east-1:123456789012:function:ats-pulse"])
    error_message = "Scheduler policy must only allow lambda:InvokeFunction on this function."
  }

  assert {
    condition     = jsondecode(aws_iam_role.scheduler.assume_role_policy).Statement[0].Principal.Service == "scheduler.amazonaws.com"
    error_message = "Scheduler role must only be assumable by EventBridge Scheduler."
  }

  assert {
    condition     = jsondecode(aws_iam_role.scheduler.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "123456789012"
    error_message = "Scheduler role trust must be limited to this account (confused deputy)."
  }

  assert {
    condition     = aws_scheduler_schedule.this.target[0].arn == "arn:aws:lambda:us-east-1:123456789012:function:ats-pulse"
    error_message = "Schedule must target this function."
  }

  assert {
    condition     = aws_scheduler_schedule.this.target[0].role_arn == "arn:aws:iam::123456789012:role/ats-pulse-scheduler"
    error_message = "Schedule must use the scheduler role."
  }

  assert {
    condition     = aws_scheduler_schedule.this.schedule_expression_timezone == "America/Mexico_City"
    error_message = "Schedule must run in the America/Mexico_City timezone."
  }
}

run "log_group_retention_is_14_days" {
  command = plan

  assert {
    condition     = aws_cloudwatch_log_group.lambda.retention_in_days == 14
    error_message = "Log group retention must be 14 days."
  }

  assert {
    condition     = aws_lambda_function.this.logging_config[0].log_group == "/aws/lambda/ats-pulse"
    error_message = "Lambda must log to the Terraform-managed log group."
  }
}

run "dynamodb_is_on_demand" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.this.billing_mode == "PAY_PER_REQUEST"
    error_message = "DynamoDB table must use on-demand (PAY_PER_REQUEST) billing."
  }

  assert {
    condition     = aws_dynamodb_table.this.hash_key == "pk"
    error_message = "DynamoDB partition key must be pk."
  }
}

run "notification_email_stays_sensitive" {
  command = apply

  assert {
    condition     = issensitive(var.notification_email)
    error_message = "notification_email must be marked sensitive."
  }

  # The identity ARN contains the email, so the policy must be hidden in plans
  assert {
    condition     = issensitive(aws_iam_role_policy.lambda.policy)
    error_message = "Lambda policy embeds the SES identity ARN and must be sensitive."
  }

  assert {
    condition     = issensitive(aws_lambda_function.this.environment[0].variables["NOTIFICATION_EMAIL"])
    error_message = "NOTIFICATION_EMAIL in the Lambda environment must be sensitive."
  }
}

run "rejects_invalid_email" {
  command = plan

  variables {
    notification_email = "not-an-email"
  }

  expect_failures = [var.notification_email]
}
