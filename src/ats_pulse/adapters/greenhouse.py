"""Greenhouse job board API: https://boards-api.greenhouse.io/v1/boards/<slug>/jobs

The API has no server-side filters, so the whole board is fetched and filtered
here like any other source. The plain list (no ?content=true) is used: content
adds every description and departments, ~12x the size, and Greenhouse
departments are often team names ("Lyft Business") that say little about the
role. Instead the department is taken from a custom metadata field companies use
to group their jobs, e.g. "Software Engineering". Boards without that field get
an empty department and rely on the title rule.
"""

import urllib.parse

from ..config import Source
from ..fetch import SourceError, get_json
from ..models import Job

API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
CATEGORY_FIELD = "Career Site Category"


def fetch_jobs(source: Source, get=get_json) -> tuple[list[Job], int]:
    payload = get(API_URL.format(slug=urllib.parse.quote(source.slug, safe="")))
    return parse(payload, source)


def parse(payload, source: Source) -> tuple[list[Job], int]:
    """Normalize a response. Returns (jobs, skipped) where skipped counts malformed postings."""
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SourceError("unexpected Greenhouse response: no 'jobs' list")

    jobs, skipped = [], 0
    for raw in payload["jobs"]:
        try:
            jobs.append(_normalize(raw, source))
        except (AttributeError, KeyError, TypeError, ValueError):
            skipped += 1
    return jobs, skipped


def _normalize(raw: dict, source: Source) -> Job:
    job_id, title = str(raw["id"]).strip(), raw["title"].strip()
    if not job_id or not title:
        raise ValueError("job without id or title")

    return Job(
        job_id=job_id,
        source=source.key,
        company=source.company,
        title=title,
        location=((raw.get("location") or {}).get("name") or "").strip(),
        department=_category(raw.get("metadata")),
        url=str(raw.get("absolute_url") or "").strip(),
        published_at=str(raw.get("first_published") or ""),
    )


def _category(metadata) -> str:
    for field in metadata or []:
        if field.get("name") == CATEGORY_FIELD:
            value = field.get("value")
            if isinstance(value, list):  # multi_select fields
                return ", ".join(str(v).strip() for v in value if v)
            return str(value or "").strip()
    return ""
