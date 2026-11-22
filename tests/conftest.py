import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID
from moto.ses.models import ses_backends

from ats_pulse.config import Source
from ats_pulse.models import Job
from ats_pulse.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
TABLE_NAME = "ats-pulse-test"
EMAIL = "test@example.com"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    """Fake credentials so nothing can ever reach a real AWS account."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "TF_VAR_notification_email"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def table(aws):
    return boto3.resource("dynamodb").create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def ses(aws):
    """sesv2 client with the notification address already verified."""
    client = boto3.client("sesv2")
    client.create_email_identity(EmailIdentity=EMAIL)
    return client


def sent_emails() -> list:
    """Messages moto accepted (it keeps the HTML body when there is one)."""
    return ses_backends[DEFAULT_ACCOUNT_ID]["us-east-1"].sent_messages


@pytest.fixture
def store(table):
    return Store(table)


@pytest.fixture
def nubank():
    return Source(company="Nubank", ats="ashby", slug="nubank")


@pytest.fixture
def ashby_payload():
    """Real Nubank response (2026-11-21), trimmed to 26 jobs, descriptions removed."""
    return json.loads((FIXTURES / "ashby_nubank.json").read_text(encoding="utf-8"))


@pytest.fixture
def lyft():
    return Source(company="Lyft", ats="greenhouse", slug="lyft")


@pytest.fixture
def greenhouse_payload():
    """Real Lyft response (2026-11-21), trimmed to 15 jobs (all 5 in Mexico)."""
    return json.loads((FIXTURES / "greenhouse_lyft.json").read_text(encoding="utf-8"))


def make_job(**overrides) -> Job:
    fields = {
        "job_id": "job-1",
        "source": "ashby:acme",
        "company": "Acme",
        "title": "Senior Software Engineer",
        "location": "Ciudad de México",
        "department": "Engineering",
        "url": "https://jobs.example.com/acme/job-1",
        "published_at": "2026-11-20T10:00:00+00:00",
        "countries": ("Mexico",),
    }
    fields.update(overrides)
    return Job(**fields)


class FakeNotifier:
    """Records what would be sent. Set fail_digest / fail_alert to make a send raise."""

    def __init__(self):
        self.digests, self.alerts = [], []
        self.fail_digest = self.fail_alert = False

    def send_digest(self, new_jobs):
        if self.fail_digest:
            raise RuntimeError("SES is down")
        self.digests.append(new_jobs)

    def send_alert(self, alerts):
        if self.fail_alert:
            raise RuntimeError("SES is down")
        self.alerts.append(alerts)


@pytest.fixture
def notifier():
    return FakeNotifier()
