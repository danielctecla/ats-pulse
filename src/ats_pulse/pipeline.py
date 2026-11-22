"""Per source: fetch -> Mexico -> engineering -> dedupe. Then notify and save.

A failing source is logged and counted in its health item; the others still run.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .adapters import ADAPTERS
from .config import Source
from .filters import is_engineering, is_mexico, mexico_location
from .notify import NewJob, SourceAlert
from .store import Store

logger = logging.getLogger(__name__)

ALERT_AFTER_FAILURES = 2  # alert once, when a source reaches this many failures in a row


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


def run(sources: list[Source], store: Store, notifier, adapters=ADAPTERS, now=utc_now) -> dict:
    results, alerts = [], []

    for source in sources:
        try:
            result = process_source(source, store, adapters)
        except Exception as exc:  # any source failure must not stop the others
            error = f"{type(exc).__name__}: {exc}"
            result = SourceResult(source, errors=1, error=error)
            failures = store.record_failure(source.company, error)
            if failures == ALERT_AFTER_FAILURES:
                alerts.append(SourceAlert(source.company, source.key, failures, error))
            logger.warning("source summary", extra=result.log_fields())
        else:
            store.record_success(source.company, now())
            logger.info("source summary", extra=result.log_fields())
        results.append(result)

    if alerts:
        notifier.send_alert(alerts)

    # Save only after the digest went out: if sending fails, the run fails and
    # the same jobs are picked up again next run instead of being lost.
    new_jobs = [n for r in results for n in r.new_jobs]
    if new_jobs:
        notifier.send_digest(new_jobs)
        first_seen_at = now()
        for n in new_jobs:
            store.save_job(n.job, n.location, first_seen_at)

    summary = {
        "sources": len(results),
        "failed_sources": sum(1 for r in results if r.error),
        "new": len(new_jobs),
        "alerts": len(alerts),
    }
    logger.info("run summary", extra=summary)
    return summary
