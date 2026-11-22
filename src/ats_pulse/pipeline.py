"""Per source: fetch -> Mexico -> engineering -> dedupe. Then notify and save.

A failing source is logged and counted in its health item; the others still run.
The alert and the digest are sent independently: if either email fails, the
other still goes out, and the run raises at the end so the crash alarm fires.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .adapters import ADAPTERS
from .config import Source
from .filters import is_engineering, is_mexico, mexico_location
from .models import NewJob, SourceAlert
from .store import MAX_ERROR_LENGTH, Store

logger = logging.getLogger(__name__)

ALERT_AFTER_FAILURES = 2  # alert once per outage, from this many failures in a row


class NotificationError(RuntimeError):
    """An email could not be sent. Raised after the run so the crash alarm fires."""


@dataclass
class SourceResult:
    source: Source
    fetched: int = 0
    mexico: int = 0
    engineering: int = 0
    new_jobs: list[NewJob] = field(default_factory=list)
    errors: int = 0  # malformed postings skipped, plus 1 if the source failed
    error: str | None = None

    def log_fields(self) -> dict:
        fields = {
            "source": self.source.key,
            "company": self.source.company,
            "fetched": self.fetched,
            "mexico": self.mexico,
            "engineering": self.engineering,
            "new": len(self.new_jobs),
            "errors": self.errors,
        }
        if self.error:
            fields["error"] = self.error
        return fields


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def process_source(source: Source, store: Store, adapters=ADAPTERS) -> SourceResult:
    jobs, skipped = adapters[source.ats](source)
    mexico = [j for j in jobs if is_mexico(j)]
    engineering = [j for j in mexico if is_engineering(j)]
    seen = store.existing_pks([j.pk for j in engineering])
    new = [NewJob(j, mexico_location(j)) for j in engineering if j.pk not in seen]
    return SourceResult(source, len(jobs), len(mexico), len(engineering), new, skipped)


def try_send(send, items: list, kind: str, failed: list[str]) -> bool:
    """Send one email. On failure log it, add it to failed and return False."""
    try:
        send(items)
    except Exception:
        logger.exception(f"{kind} email failed", extra={"items": len(items)})
        failed.append(kind)
        return False
    return True


def run(sources: list[Source], store: Store, notifier, adapters=ADAPTERS, now=utc_now) -> dict:
    results, alerts = [], []

    for source in sources:
        try:
            result = process_source(source, store, adapters)
        except Exception as exc:  # any source failure must not stop the others
            error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
            result = SourceResult(source, errors=1, error=error)
            failures, alert_sent = store.record_failure(source.company, error)
            # ">=" rather than "==": an alert whose email failed is retried next run
            if failures >= ALERT_AFTER_FAILURES and not alert_sent:
                alerts.append(SourceAlert(source.company, source.key, failures, error))
            logger.warning("source summary", extra=result.log_fields())
        else:
            store.record_success(source.company, now())
            logger.info("source summary", extra=result.log_fields())
        results.append(result)

    # Send both emails before any bookkeeping, so neither a failed send nor a
    # failed DynamoDB write can hold back the other email.
    failed_emails = []
    new_jobs = [n for r in results for n in r.new_jobs]
    alert_ok = bool(alerts) and try_send(notifier.send_alert, alerts, "alert", failed_emails)
    digest_ok = bool(new_jobs) and try_send(notifier.send_digest, new_jobs, "digest", failed_emails)

    # Save only after the digest went out: if sending fails, the same jobs are
    # picked up again next run instead of being lost.
    if digest_ok:
        first_seen_at = now()
        for n in new_jobs:
            store.save_job(n.job, n.location, first_seen_at)
    # Mark only after the alert went out, so a failed alert is retried next run.
    if alert_ok:
        for alert in alerts:
            store.mark_alert_sent(alert.company)

    summary = {
        "sources": len(results),
        "failed_sources": sum(1 for r in results if r.error),
        "new": len(new_jobs),
        "alerts": len(alerts),
    }
    logger.info("run summary", extra={**summary, "failed_emails": failed_emails})
    if failed_emails:
        raise NotificationError(f"could not send: {', '.join(failed_emails)}")
    return summary
