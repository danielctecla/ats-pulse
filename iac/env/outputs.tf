# No output exposes the notification email or the SES identity ARN (which contains it).

output "function_name" {
  description = "Lambda function name, for manual invokes."
  value       = aws_lambda_function.this.function_name
}

output "log_group_name" {
  description = "CloudWatch log group of the function."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "schedule_name" {
  description = "EventBridge Scheduler schedule name (default group)."
  value       = aws_scheduler_schedule.this.name
}

output "table_name" {
  description = "DynamoDB table with job and health items."
  value       = aws_dynamodb_table.this.name
}
