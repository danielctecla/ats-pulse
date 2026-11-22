"""Run the real pipeline against the live job-board APIs with an in-memory
(moto) DynamoDB. Nothing touches AWS. Runs twice to show deduplication.

    make run-local
"""

import json
import logging
import os
import sys

# Fake credentials before boto3 loads: this script must never reach a real account
os.environ.update(
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_DEFAULT_REGION="us-east-1",
)
for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
    os.environ.pop(name, None)

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from ats_pulse import pipeline  # noqa: E402
from ats_pulse.config import load_sources  # noqa: E402
from ats_pulse.store import Store  # noqa: E402

STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonLines(logging.Formatter):
    """Roughly what the Lambda JSON log format writes to CloudWatch."""

    def format(self, record):
        extra = {k: v for k, v in vars(record).items() if k not in STANDARD_ATTRS}
        return json.dumps({"level": record.levelname, "message": record.getMessage(), **extra}, ensure_ascii=False)


class PrintNotifier:
    def send_digest(self, new_jobs):
        print(f"\n  Digest would contain {len(new_jobs)} job(s):")
        for n in sorted(new_jobs, key=lambda n: (n.job.company, n.job.title)):
            print(f"   - [{n.job.company}] {n.job.title}")
            print(f"       {n.location} | published {n.job.published_at[:10]} | {n.job.url}")

    def send_alert(self, alerts):
        print(f"\n  Alert would list {len(alerts)} failing source(s):")
        for a in alerts:
            print(f"   - {a.company} ({a.source}): {a.last_error}")


def main():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLines())
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("ats_pulse").setLevel(logging.INFO)

    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="ats-pulse-local",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        store, sources = Store(table), load_sources()

        for label in ("Run 1 (empty table)", "Run 2 (same table, should find nothing new)"):
            print(f"\n=== {label} ===")
            pipeline.run(sources, store, PrintNotifier())

        items = table.scan()["Items"]
        jobs = sum(1 for i in items if i["pk"].startswith("job#"))
        print(f"\n=== Table after both runs: {jobs} job item(s), {len(items) - jobs} health item(s) ===")
        for item in items:
            if item["pk"].startswith("health#"):
                print(f"   {item['pk']}: consecutive_failures={item['consecutive_failures']}")


if __name__ == "__main__":
    main()
