locals {
  src_dir = "${path.module}/../../src"

  # The identity ARN embeds the email address, so mark it sensitive: anything
  # built from it (the Lambda policy) is then hidden in plan output.
  ses_identity_arn = sensitive(aws_sesv2_email_identity.notification.arn)
}
