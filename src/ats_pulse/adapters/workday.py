"""Workday career sites: https://<tenant>.<wdN>.myworkdayjobs.com/<site>

The slug is "<tenant>.<wdN>/<site>", e.g. "acme.wd5/External_Careers".

The job list (POST .../wday/cxs/<tenant>/<site>/jobs) has no department and
returns 20 jobs per page, so paging through a big board takes 80+ requests. It
does filter by the board's facets, though. One request reads them, then only
these Mexico openings are fetched:
- the ones in an engineering job category (same rule as departments in
  filters.py), with the category as the department
- internships, whatever their category: boards often file them all under one
  (e.g. "Fixed Term & Temporary"), so the title rule picks the engineering ones
Other categories aren't matched on the title: on real data, "Solution Architect"
and "Solution Engineer" there were sales roles. A board without job categories
gets all its Mexico openings, matched on the title only.
"""

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from ..config import Source
from ..fetch import SourceError, post_json
from ..filters import is_engineering_department
from ..models import Job

API_URL = "https://{host}/wday/cxs/{tenant}/{site}/jobs"
JOB_URL = "https://{host}/{site}{path}"
PAGE_SIZE = 20  # the API's maximum: more is a 400
CATEGORY_FACET = "jobFamilyGroup"
JOB_TYPE_FACET = "workerSubType"
MEXICO = {"mexico", "méxico"}

_POSTED = re.compile(r"^posted (today|yesterday|(\d+) days? ago)$", re.IGNORECASE)
_SEVERAL_LOCATIONS = re.compile(r"^(\d+) locations$", re.IGNORECASE)


def fetch_jobs(source: Source, post=post_json, today: date | None = None) -> tuple[list[Job], int]:
    tenant_host, _, site = source.slug.partition("/")
    if "." not in tenant_host or not site:
        raise SourceError(f"Workday slug must look like <tenant>.<wdN>/<site>, got {source.slug!r}")
    host = f"{tenant_host}.myworkdayjobs.com"
    url = API_URL.format(host=host, tenant=tenant_host.split(".")[0], site=site)
    today = today or datetime.now(UTC).date()

    facets = _page(post, url, {}, 0, limit=1).get("facets")
    if not isinstance(facets, list):
        raise SourceError("unexpected Workday response: no 'facets' list")
    values = list(_facet_values(facets))

    # Country facets first: a location facet can also have a value named "Mexico"
    mexico = sorted(
        ((param, v) for param, v in values if str(v.get("descriptor", "")).strip().casefold() in MEXICO),
        key=lambda m: "country" not in str(m[0]).lower(),
    )
    if not mexico:
        return [], 0  # no openings in Mexico right now
    param, country = mexico[0]
    in_mexico = {param: [country["id"]]}

    categories = [v for param, v in values if param == CATEGORY_FACET]
    # (facets, department, employment type) of each query
    queries = [
        ({CATEGORY_FACET: [c["id"]]}, c["descriptor"], "")
        for c in categories
        if is_engineering_department(c.get("descriptor", ""))
    ]
    if not categories:
        queries.append(({}, "", ""))
    queries += [
        ({JOB_TYPE_FACET: [v["id"]]}, "", "Internship")
        for param, v in values
        if param == JOB_TYPE_FACET and str(v.get("descriptor", "")).casefold().startswith("intern")
    ]

    jobs, skipped = {}, 0
    for facet, department, employment_type in queries:
        for raw in _postings(post, url, {**in_mexico, **facet}):
            try:
                job = _normalize(raw, source, host, site, country["descriptor"], today)
            except (AttributeError, KeyError, TypeError, ValueError):
                skipped += 1
                continue
            # An internship in an engineering category comes up twice: keep both details
            seen = jobs.get(job.job_id, job)
            jobs[job.job_id] = replace(
                seen,
                department=department or seen.department,
                employment_type=employment_type or seen.employment_type,
            )
    return list(jobs.values()), skipped


def _page(post, url: str, facets: dict, offset: int, limit: int = PAGE_SIZE) -> dict:
    payload = post(url, {"appliedFacets": facets, "limit": limit, "offset": offset, "searchText": ""})
    if not isinstance(payload, dict) or not isinstance(payload.get("jobPostings"), list):
        raise SourceError("unexpected Workday response: no 'jobPostings' list")
    return payload


def _postings(post, url: str, facets: dict):
    first = _page(post, url, facets, 0)
    total = first.get("total")  # only the first page has it; the others say 0
    if not isinstance(total, int):
        raise SourceError("unexpected Workday response: no 'total'")
    yield from first["jobPostings"]
    for offset in range(PAGE_SIZE, total, PAGE_SIZE):
        postings = _page(post, url, facets, offset)["jobPostings"]
        if not postings:
            break
        yield from postings


def _facet_values(facets: list):
    """(facet parameter, value) pairs, including nested facets such as locationMainGroup."""
    for facet in facets:
        for value in facet.get("values") or []:
            if "facetParameter" in value:
                yield from _facet_values([value])
            else:
                yield facet.get("facetParameter"), value


def _normalize(raw: dict, source: Source, host: str, site: str, country: str, today: date) -> Job:
    path, title = raw["externalPath"].strip(), raw["title"].strip()
    if not path or not title:
        raise ValueError("job without path or title")

    location = (raw.get("locationsText") or "").strip()
    if several := _SEVERAL_LOCATIONS.match(location):  # "5 Locations": one of them is in Mexico
        location = f"{country} and {int(several[1]) - 1} more"

    return Job(
        job_id=path.rsplit("_", 1)[-1],  # "/job/Mexico---Mexico-City/Software-Engineer_JR123-1" -> "JR123-1"
        source=source.key,
        company=source.company,
        title=title,
        location=location,
        department="",
        url=JOB_URL.format(host=host, site=site, path=path),
        published_at=_posted_on(raw.get("postedOn"), today),
        countries=(country,),
    )


def _posted_on(text, today: date) -> str:
    """'Posted 3 Days Ago' -> ISO date. Empty for 'Posted 30+ Days Ago': only that it's old is known."""
    match = _POSTED.match(str(text or "").strip())
    if not match:
        return ""
    when = match[1].lower()
    days = 0 if when == "today" else 1 if when == "yesterday" else int(match[2])
    return (today - timedelta(days=days)).isoformat()
