"""Sends the digest and alerts through SES (v2 API).

The notification address is both sender and recipient (the verified SES
identity), so the account can stay in the SES sandbox. It is never logged:
SES error messages can contain it, so they are redacted before being raised.
"""

import logging
import re
from email.utils import formataddr

from botocore.exceptions import ClientError

from . import emails
from .models import NewJob, SourceAlert

logger = logging.getLogger(__name__)

SENDER_NAME = "ats-pulse"


class EmailError(RuntimeError):
    """SES rejected or failed a send. The message never contains the address."""


class SesNotifier:
    def __init__(self, client, address: str, logos: dict[str, str] | None = None):
        """client: a boto3 sesv2 client. address: the verified identity. logos: company -> image URL."""
        self.client = client
        self.address = address
        self.logos = logos or {}

    def send_digest(self, new_jobs: list[NewJob]) -> None:
        self._send("digest", emails.digest(new_jobs, logos=self.logos))

    def send_alert(self, alerts: list[SourceAlert]) -> None:
        self._send("alert", emails.alert(alerts))

    def _send(self, kind: str, email: emails.Email) -> None:
        body = {"Text": {"Data": email.text, "Charset": "UTF-8"}}
        if email.html:
            body["Html"] = {"Data": email.html, "Charset": "UTF-8"}
        try:
            response = self.client.send_email(
                FromEmailAddress=formataddr((SENDER_NAME, self.address)),
                Destination={"ToAddresses": [self.address]},
                Content={"Simple": {"Subject": {"Data": email.subject, "Charset": "UTF-8"}, "Body": body}},
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            message = self.redact(f"SES {error.get('Code', 'error')}: {error.get('Message', '')}")
            raise EmailError(f"{kind} email not sent: {message}") from None  # drop the unredacted original
        logger.info("email sent", extra={"kind": kind, "message_id": response["MessageId"]})

    def redact(self, text: str) -> str:
        return re.sub(re.escape(self.address), "<notification email>", text, flags=re.IGNORECASE)
