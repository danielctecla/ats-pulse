"""DynamoDB access: seen jobs and source health, in one table keyed by pk.

Uses only the actions the Lambda role allows: BatchGetItem, GetItem, PutItem, UpdateItem.
"""

import time

from botocore.exceptions import ClientError

from .models import Job

BATCH_GET_LIMIT = 100  # DynamoDB maximum keys per BatchGetItem
MAX_ERROR_LENGTH = 500


class Store:
    def __init__(self, table):
        """table: a boto3 DynamoDB Table resource."""
        self.table = table
        # The resource's client serializes plain Python values (no {"S": ...} wrappers)
        self.client = table.meta.client

    # --- jobs -------------------------------------------------------------
    def existing_pks(self, pks: list[str]) -> set[str]:
        """Which of these keys are already in the table (BatchGetItem, 100 at a time)."""
        unique = list(dict.fromkeys(pks))  # BatchGetItem rejects duplicate keys
        found: set[str] = set()
        for start in range(0, len(unique), BATCH_GET_LIMIT):
            request = {
                self.table.name: {
                    "Keys": [{"pk": pk} for pk in unique[start : start + BATCH_GET_LIMIT]],
                    "ProjectionExpression": "pk",
                }
            }
            for attempt in range(5):
                response = self.client.batch_get_item(RequestItems=request)
                found.update(item["pk"] for item in response["Responses"].get(self.table.name, []))
                request = response.get("UnprocessedKeys") or {}
                if not request:
                    break
                time.sleep(0.1 * 2**attempt)  # throttled: back off and retry the rest
            else:
                raise RuntimeError("DynamoDB left keys unprocessed after 5 attempts")
        return found

    def save_job(self, job: Job, location: str, first_seen_at: str) -> None:
        try:
            self.table.put_item(
                Item=job.to_item(location, first_seen_at),
                ConditionExpression="attribute_not_exists(pk)",  # never overwrite first_seen_at
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    # --- source health ----------------------------------------------------
    def record_failure(self, company: str, error: str) -> int:
        """Increment consecutive_failures and return the new value."""
        response = self.table.update_item(
            Key={"pk": f"health#{company}"},
            UpdateExpression="ADD consecutive_failures :one SET last_error = :error",
            ExpressionAttributeValues={":one": 1, ":error": error[:MAX_ERROR_LENGTH]},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["consecutive_failures"])

    def record_success(self, company: str, now: str) -> None:
        self.table.update_item(
            Key={"pk": f"health#{company}"},
            UpdateExpression="SET consecutive_failures = :zero, last_success_at = :now",
            ExpressionAttributeValues={":zero": 0, ":now": now},
        )
