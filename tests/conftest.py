import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from ats_pulse.config import Source
from ats_pulse.models import Job
from ats_pulse.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
TABLE_NAME = "ats-pulse-test"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    """Fake credentials so nothing can ever reach a real AWS account."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "TF_VAR_notification_email"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def table():
    with mock_aws():
        yield boto3.resource("dynamodb").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


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
    def __init__(self):
        self.digests, self.alerts = [], []

    def send_digest(self, new_jobs):
        self.digests.append(new_jobs)

    def send_alert(self, alerts):
        self.alerts.append(alerts)


@pytest.fixture
def notifier():
    return FakeNotifier()
