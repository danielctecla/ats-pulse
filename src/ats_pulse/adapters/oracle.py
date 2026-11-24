"""Oracle Recruiting Cloud career sites:
https://<pod>.oraclecloud.com/hcmUI/CandidateExperience/en/sites/<site>

The slug is "<pod>/<site>", e.g. "acme.fa.us2/CX_1".

The job list (GET .../recruitingCEJobRequisitions, what the career site calls)
returns 25 jobs per page from boards of thousands, but it filters by location:
only the Mexico openings are fetched, including the ones where Mexico is a
secondary location. The department is the job family when the board fills it
in; boards that don't are matched on the title only.
"""

import urllib.parse

from ..config import Source
from ..fetch import SourceError, get_json
from ..models import Job

API_URL = (
    "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    "?onlyData=true&expand=requisitionList.secondaryLocations"
    "&finder=findReqs;siteNumber={site},location=Mexico,sortBy=POSTING_DATES_DESC,limit={limit},offset={offset}"
)
JOB_URL = "https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}"
PAGE_SIZE = 25


def fetch_jobs(source: Source, get=get_json) -> tuple[list[Job], int]:
    pod, _, site = source.slug.partition("/")
    if "." not in pod or not site:
        raise SourceError(f"Oracle slug must look like <pod>/<site>, got {source.slug!r}")
    host = f"{pod}.oraclecloud.com"

    jobs, skipped = {}, 0
    for raw in _requisitions(get, host, urllib.parse.quote(site, safe="")):
        try:
            job = _normalize(raw, source, host, site)
        except (AttributeError, KeyError, TypeError, ValueError):
            skipped += 1
            continue
        jobs[job.job_id] = job  # a job posted while paging pushes the next ones a page down
    return list(jobs.values()), skipped


def _page(get, host: str, site: str, offset: int) -> dict:
    payload = get(API_URL.format(host=host, site=site, limit=PAGE_SIZE, offset=offset))
    items = payload.get("items") if isinstance(payload, dict) else None
    search = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
    if not isinstance(search.get("requisitionList"), list) or not isinstance(search.get("TotalJobsCount"), int):
        raise SourceError("unexpected Oracle response: no 'requisitionList' or 'TotalJobsCount'")
    return search


def _requisitions(get, host: str, site: str):
    first = _page(get, host, site, 0)
    yield from first["requisitionList"]
    for offset in range(PAGE_SIZE, first["TotalJobsCount"], PAGE_SIZE):
        requisitions = _page(get, host, site, offset)["requisitionList"]
        if not requisitions:
            break
        yield from requisitions


def _normalize(raw: dict, source: Source, host: str, site: str) -> Job:
    job_id, title = str(raw["Id"]).strip(), raw["Title"].strip()
    if not job_id or not title:
        raise ValueError("job without id or title")

    secondary = raw.get("secondaryLocations") or []
    countries = [raw.get("PrimaryLocationCountry")] + [s.get("CountryCode") for s in secondary]

    return Job(
        job_id=job_id,
        source=source.key,
        company=source.company,
        title=title,
        location=(raw.get("PrimaryLocation") or "").strip(),
        department=(raw.get("JobFamily") or "").strip(),
        url=JOB_URL.format(host=host, site=site, job_id=urllib.parse.quote(job_id, safe="")),
        published_at=str(raw.get("PostedDate") or ""),
        secondary_locations=tuple(s["Name"].strip() for s in secondary if s.get("Name")),
        countries=tuple(c for c in countries if c),
    )
