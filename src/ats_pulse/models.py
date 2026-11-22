"""Common job schema every ATS adapter normalizes to, and what the emails are built from."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    job_id: str
    source: str  # Source.key, e.g. "ashby:nubank"
    company: str
    title: str
    location: str  # primary location
    department: str
    url: str
    published_at: str  # ISO 8601, as given by the ATS
    # Used by the filters only, not stored
    team: str = ""
    secondary_locations: tuple[str, ...] = field(default=())
    countries: tuple[str, ...] = field(default=())

    @property
    def pk(self) -> str:
        return f"job#{self.source}#{self.job_id}"

    def to_item(self, location: str, first_seen_at: str) -> dict:
        """DynamoDB item: only the fields worth keeping (no description, 400 KB limit)."""
        return {
            "pk": self.pk,
            "job_id": self.job_id,
            "source": self.source,
            "company": self.company,
            "title": self.title,
            "location": location,
            "department": self.department,
            "url": self.url,
            "published_at": self.published_at,
            "first_seen_at": first_seen_at,
        }


@dataclass(frozen=True)
class NewJob:
    """A job for the digest."""

    job: Job
    location: str  # display location (Mexico-aware), as stored


@dataclass(frozen=True)
class SourceAlert:
    """A source that has kept failing, for the alert email."""

    company: str
    source: str
    consecutive_failures: int
    last_error: str

