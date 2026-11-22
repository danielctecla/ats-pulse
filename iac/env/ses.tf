# Used as both sender and recipient. AWS emails a verification link after the
# first apply, and sending fails until it is clicked. In the SES sandbox only
# verified addresses can receive mail, which is fine since it only emails itself.
resource "aws_sesv2_email_identity" "notification" {
  email_identity = var.notification_email
}
