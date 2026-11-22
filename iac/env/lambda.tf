# 1. Code: src/ zipped as is (stdlib + boto3 only, no dependencies to package)
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = local.src_dir
  output_path = "${path.module}/.build/lambda.zip"
  excludes    = ["**/__pycache__/**"]

  # Same zip hash on any machine (local or CI), so plans don't show false diffs
  output_file_mode = "0644"
}

# 2. Log group, created up front so Terraform manages its retention
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = var.log_retention_days
}

# 3. Execution role: its own log group, its own table, and sending from the
#    verified identity. Nothing else.
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-lambda"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "OwnLogGroup"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
      },
      {
        Sid    = "OwnTable"
        Effect = "Allow"
        Action = [
          "dynamodb:BatchGetItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
        ]
        Resource = [aws_dynamodb_table.this.arn]
      },
      {
        Sid      = "SendFromVerifiedIdentity"
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = [local.ses_identity_arn]
      },
    ]
  })
}

# 4. Function
resource "aws_lambda_function" "this" {
  function_name    = var.project_name
  description      = "Polls ATS job boards and emails new Mexico engineering openings"
  role             = aws_iam_role.lambda.arn
  runtime          = var.lambda_runtime
  handler          = "ats_pulse.handler.lambda_handler"
  architectures    = ["arm64"]
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_seconds
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.this.name
      NOTIFICATION_EMAIL = var.notification_email
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [aws_iam_role_policy.lambda]
}

# 5. No async retries: the next scheduled run picks up where this one failed,
#    and a retry after a late crash could send the same digest or alert twice.
resource "aws_lambda_function_event_invoke_config" "this" {
  function_name          = aws_lambda_function.this.function_name
  maximum_retry_attempts = 0
}
