import logging

import boto3
import pytest

from ats_pulse.models import NewJob, SourceAlert
from ats_pulse.notify import EmailError, SesNotifier

from conftest import EMAIL, make_job, sent_emails

ALERT = SourceAlert("Acme", "ashby:acme", 2, "SourceError: HTTP 503")


def test_sends_digest_to_and_from_the_notification_address(ses):
    SesNotifier(ses, EMAIL).send_digest([NewJob(make_job(), "Ciudad de México")])

    [message] = sent_emails()
    assert message.source == f"ats-pulse <{EMAIL}>"
    assert message.destinations["ToAddresses"] == [EMAIL]
    assert message.subject == "1 new engineering job in Mexico: Acme"


class RecordingClient:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "m-1"}


def test_digest_has_html_and_text_parts_alert_only_text():
    client = RecordingClient()
    notifier = SesNotifier(client, EMAIL)
    notifier.send_digest([NewJob(make_job(), "Ciudad de México")])
    notifier.send_alert([ALERT])

    digest_body, alert_body = (c["Content"]["Simple"]["Body"] for c in client.calls)
    assert set(digest_body) == {"Html", "Text"}
    assert set(alert_body) == {"Text"}
    assert digest_body["Text"]["Charset"] == "UTF-8"


def test_ses_error_is_raised_without_the_address(aws, caplog):
    """SES error messages include the address; it must not reach the logs."""
    caplog.set_level(logging.INFO)
    notifier = SesNotifier(boto3.client("sesv2"), EMAIL)  # identity not verified

    with pytest.raises(EmailError) as excinfo:
        notifier.send_alert([ALERT])

    assert "alert email not sent: SES MessageRejected" in str(excinfo.value)
    assert EMAIL not in str(excinfo.value)
    assert excinfo.value.__suppress_context__  # original error not chained into tracebacks
    assert EMAIL not in caplog.text


def test_address_is_never_logged_on_success(ses, caplog):
    caplog.set_level(logging.DEBUG, logger="ats_pulse")
    SesNotifier(ses, EMAIL).send_alert([ALERT])

    assert "email sent" in caplog.text
    assert EMAIL not in caplog.text
