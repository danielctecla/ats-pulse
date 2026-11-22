"""Where the digest and alerts go.

Phase 2 placeholder: LogNotifier only logs counts. Phase 3 adds the SES notifier.
"""

import logging
from dataclasses import dataclass

from .models import Job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewJob:
    job: Job
    location: str  # display location (Mexico-aware), as stored


@dataclass(frozen=True)
class SourceAlert:
    company: str
    source: str
    consecutive_failures: int
    last_error: str


class LogNotifier:
    def send_digest(self, new_jobs: list[NewJob]) -> None:
        logger.info("digest not sent (email arrives in Phase 3)", extra={"new": len(new_jobs)})

    def send_alert(self, alerts: list[SourceAlert]) -> None:
        logger.warning(
            "alert not sent (email arrives in Phase 3)",
            extra={"failing_sources": [a.source for a in alerts]},
        )
