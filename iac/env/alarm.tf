# Backstop for failures the code can't report itself: timeout, out of memory,
# import error, unhandled exception. Per-source API failures are handled in code
# and alerted by SES. This path uses SNS so it still works when the Lambda or
# SES is what's broken.

# Not KMS-encrypted on purpose: CloudWatch can't publish to a topic encrypted with
# the AWS-managed SNS key, and a customer-managed key costs $1/month. Messages
# only carry the alarm name and state.
resource "aws_sns_topic" "alarms" {
  name = "${var.project_name}-alarms"
}

# AWS emails a confirmation link after apply; nothing is delivered until it's clicked.
resource "aws_sns_topic_subscription" "alarm_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name        = "${var.project_name}-lambda-errors"
  alarm_description = "The ${var.project_name} Lambda failed (crash, timeout or unhandled error). Check its CloudWatch logs."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = aws_lambda_function.this.function_name }
  statistic   = "Sum"

  # Any failed invocation within an hour; no data (no runs) is not an error
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
}
