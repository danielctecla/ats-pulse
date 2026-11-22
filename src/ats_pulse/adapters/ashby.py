"""Ashby public posting API: https://api.ashbyhq.com/posting-api/job-board/<slug>"""

import urllib.parse

from ..config import Source
from ..fetch import SourceError, get_json
from ..models import Job

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch_jobs(source: Source, get=get_json) -> tuple[list[Job], int]:
    payload = get(API_URL.format(slug=urllib.parse.quote(source.slug, safe="")))
    return parse(payload, source)


def parse(payload, source: Source) -> tuple[list[Job], int]:
    """Normalize a response. Returns (jobs, skipped) where skipped counts malformed postings."""
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SourceError("unexpected Ashby response: no 'jobs' list")

    jobs, skipped = [], 0
    for raw in payload["jobs"]:
        try:
            if raw.get("isListed") is False:
                continue
            jobs.append(_normalize(raw, source))
        except (AttributeError, KeyError, TypeError, ValueError):
            skipped += 1
    return jobs, skipped


def _normalize(raw: dict, source: Source) -> Job:
    job_id, title = str(raw["id"]).strip(), raw["title"].strip()
    if not job_id or not title:
        raise ValueError("job without id or title")

    secondary = raw.get("secondaryLocations") or []
    countries = [_country(raw.get("address"))] + [_country(s.get("address")) for s in secondary]

    return Job(
        job_id=job_id,
        source=source.key,
        company=source.company,
        title=title,
        location=(raw.get("location") or "").strip(),
        department=(raw.get("department") or "").strip(),
        team=(raw.get("team") or "").strip(),
        url=str(raw.get("jobUrl") or raw.get("applyUrl") or "").strip(),
        published_at=str(raw.get("publishedAt") or ""),
        secondary_locations=tuple(s["location"].strip() for s in secondary if s.get("location")),
        countries=tuple(c for c in countries if c),
    )


def _country(address) -> str | None:
    return ((address or {}).get("postalAddress") or {}).get("addressCountry")
