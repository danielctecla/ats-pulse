"""Run the real pipeline against the live job-board APIs with an in-memory
(moto) DynamoDB. Nothing touches AWS and no email is sent: each email's text is
printed and the digest's HTML is written to preview.html. Runs twice to show
deduplication.

    make run-local
"""

import json
import logging
import os
import sys
import textwrap
from pathlib import Path

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

from ats_pulse import emails, pipeline  # noqa: E402
from ats_pulse.config import load_sources  # noqa: E402
from ats_pulse.store import Store  # noqa: E402

STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
PREVIEW = Path(__file__).resolve().parents[1] / "preview.html"  # gitignored


class JsonLines(logging.Formatter):
    """Roughly what the Lambda JSON log format writes to CloudWatch."""

    def format(self, record):
        extra = {k: v for k, v in vars(record).items() if k not in STANDARD_ATTRS}
        return json.dumps({"level": record.levelname, "message": record.getMessage(), **extra}, ensure_ascii=False)


class PreviewNotifier:
    """Prints each email instead of sending it; the digest HTML goes to preview.html."""

    def send_digest(self, new_jobs):
        email = emails.digest(new_jobs)
        PREVIEW.write_text(email.html, encoding="utf-8")
        self.show(email, f"HTML version written to {PREVIEW}")

    def send_alert(self, alerts):
        self.show(emails.alert(alerts))

    @staticmethod
    def show(email, note=""):
        print(f"\n  Subject: {email.subject}")
        print(textwrap.indent(email.text, "  | ", lambda line: True), end="")
        if note:
            print(f"  ({note})")


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
            pipeline.run(sources, store, PreviewNotifier())

        items = table.scan()["Items"]
        jobs = sum(1 for i in items if i["pk"].startswith("job#"))
        print(f"\n=== Table after both runs: {jobs} job item(s), {len(items) - jobs} health item(s) ===")
        for item in items:
            if item["pk"].startswith("health#"):
                print(f"   {item['pk']}: consecutive_failures={item['consecutive_failures']}")


if __name__ == "__main__":
    main()
