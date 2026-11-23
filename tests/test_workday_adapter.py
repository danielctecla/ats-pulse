from datetime import date

import pytest

from ats_pulse.adapters import workday
from ats_pulse.config import Source
from ats_pulse.fetch import SourceError

from conftest import WORKDAY_RECORDED_ON, replay

ACME = Source(company="Acme", ats="workday", slug="acme.wd5/Careers")
TODAY = date(2026, 11, 23)
MEXICO = {"facetParameter": "locationCountry", "values": [{"descriptor": "Mexico", "id": "mx", "count": 9}]}
IN_MEXICO = {"locationCountry": ["mx"]}


def facet(parameter, **values):
    return {"facetParameter": parameter, "values": [{"descriptor": d, "id": i, "count": 1} for i, d in values.items()]}


def posting(n, title="Software Engineer", where="Mexico - Mexico City", posted="Posted Today"):
    return {"title": title, "externalPath": f"/job/Mexico---Mexico-City/Job_JR{n}", "locationsText": where, "postedOn": posted}


def fake_board(facets, postings):
    """Pages like the real API: 20 at a time, the total only on the first page.

    postings(applied_facets) returns the jobs a query matches. Returns (post, requests).
    """
    requests = []

    def post(url, payload):
        requests.append(payload["appliedFacets"])
        if payload["limit"] == 1:  # the facet listing
            return {"total": 1600, "jobPostings": [posting(0)], "facets": facets}
        found, offset = postings(payload["appliedFacets"]), payload["offset"]
        return {"total": len(found) if offset == 0 else 0, "jobPostings": found[offset : offset + payload["limit"]]}

    return post, requests


def test_fetches_mexico_engineering_categories_from_real_board(salesforce, workday_recording):
    jobs, skipped = workday.fetch_jobs(salesforce, post=replay(workday_recording), today=WORKDAY_RECORDED_ON)

    assert (len(jobs), skipped) == (12, 0)
    assert {j.department for j in jobs} == {"Software Engineering", "Enterprise Technology & Infrastructure"}
    assert all(j.countries == ("Mexico",) for j in jobs)

    job = next(j for j in jobs if j.job_id == "JR363732")
    assert job.title == "Systems Senior Analyst"  # matched by its category, not its title
    assert job.location == "Mexico - Mexico City"
    assert job.department == "Enterprise Technology & Infrastructure"
    assert job.url == (
        "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/Mexico---Mexico-City/Systems-Senior-Analyst_JR363732"
    )
    assert job.published_at == "2026-11-17"  # "Posted 6 Days Ago"
    assert job.pk == "job#workday:salesforce.wd12/External_Career_Site#JR363732"


def test_queries_only_mexico_and_engineering_categories(salesforce, workday_recording):
    """Sales and Customer Success aren't requested, so their "Solution Architect"s never show up."""
    requests = []

    def post(url, payload):
        requests.append(payload["appliedFacets"])
        return replay(workday_recording)(url, payload)

    workday.fetch_jobs(salesforce, post=post, today=WORKDAY_RECORDED_ON)

    listing = workday_recording[0]["response"]["facets"]
    names = {v["id"]: v["descriptor"] for f in listing if f["facetParameter"] == "jobFamilyGroup" for v in f["values"]}
    asked = [names[r["jobFamilyGroup"][0]] for r in requests if "jobFamilyGroup" in r]
    assert asked == ["Software Engineering", "Enterprise Technology & Infrastructure", "Data"]
    assert all(len(r) == 2 for r in requests[1:])  # Mexico plus one category or job type


def test_pages_through_all_results():
    post, requests = fake_board(
        [MEXICO, facet("jobFamilyGroup", se="Software Engineering")],
        lambda applied: [posting(n) for n in range(45)] if applied == {**IN_MEXICO, "jobFamilyGroup": ["se"]} else [],
    )
    jobs, _ = workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert len(jobs) == 45
    assert len(requests) == 1 + 3  # facet listing, then 3 pages of 20


def test_internships_are_fetched_from_any_category():
    engineering_intern, sales_intern = posting(1, "Software Engineer Intern"), posting(2, "Sales Intern")
    queries = {
        "se": [engineering_intern],
        "intern": [engineering_intern, sales_intern],
    }
    post, requests = fake_board(
        [
            MEXICO,
            facet("jobFamilyGroup", se="Software Engineering", sales="Sales", temp="Fixed Term & Temporary"),
            facet("workerSubType", regular="Regular", intern="Intern (Fixed Term)"),
        ],
        lambda applied: queries[(applied.get("jobFamilyGroup") or applied.get("workerSubType"))[0]],
    )
    jobs, _ = workday.fetch_jobs(ACME, post=post, today=TODAY)

    by_id = {j.job_id: j for j in jobs}
    assert (by_id["JR1"].department, by_id["JR1"].employment_type) == ("Software Engineering", "Internship")
    # The title rule in filters.py decides on this one
    assert (by_id["JR2"].department, by_id["JR2"].employment_type) == ("", "Internship")
    assert requests[1:] == [{**IN_MEXICO, "jobFamilyGroup": ["se"]}, {**IN_MEXICO, "workerSubType": ["intern"]}]


def test_no_openings_in_mexico_is_one_request():
    post, requests = fake_board([facet("locationCountry", us="United States of America")], lambda applied: [])

    assert workday.fetch_jobs(ACME, post=post, today=TODAY) == ([], 0)
    assert len(requests) == 1


def test_board_without_categories_gets_every_mexico_opening():
    post, requests = fake_board([MEXICO], lambda applied: [posting(1, "Account Executive")])
    jobs, _ = workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert [j.title for j in jobs] == ["Account Executive"]  # left to the title rule
    assert requests[1:] == [IN_MEXICO]


def test_prefers_the_country_facet_over_a_location_named_mexico():
    locations = {
        "facetParameter": "locationMainGroup",
        "values": [facet("locations", **{"loc-mx": "Mexico"})],  # nested, like on real boards
    }
    post, requests = fake_board([locations, MEXICO], lambda applied: [])
    workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert requests[1:] == [IN_MEXICO]


@pytest.mark.parametrize(
    "posted, published_at",
    [
        ("Posted Today", "2026-11-23"),
        ("Posted Yesterday", "2026-11-22"),
        ("Posted 1 Day Ago", "2026-11-22"),
        ("Posted 6 Days Ago", "2026-11-17"),
        ("Posted 30+ Days Ago", ""),  # only that it's old is known
        (None, ""),
        ("Nov 17", ""),
    ],
)
def test_posting_date_from_relative_text(posted, published_at):
    post, _ = fake_board([MEXICO], lambda applied: [posting(1, posted=posted)])
    [job], _ = workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert job.published_at == published_at


def test_several_locations_say_mexico_is_one_of_them():
    post, _ = fake_board([MEXICO], lambda applied: [posting(1, where="5 Locations")])
    [job], _ = workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert job.location == "Mexico and 4 more"


def test_skips_malformed_postings():
    malformed = [{"title": "No path"}, {"externalPath": "/job/x_JR9", "title": "  "}, "not-a-job"]
    post, _ = fake_board([MEXICO], lambda applied: [posting(1), *malformed])
    jobs, skipped = workday.fetch_jobs(ACME, post=post, today=TODAY)

    assert [j.job_id for j in jobs] == ["JR1"]
    assert skipped == 3


@pytest.mark.parametrize(
    "response",
    [{"errorCode": "HTTP_404"}, {"jobPostings": []}, []],
    ids=["error", "no-facets", "not-an-object"],
)
def test_rejects_unexpected_response_shape(response):
    with pytest.raises(SourceError, match="unexpected Workday response"):
        workday.fetch_jobs(ACME, post=lambda url, payload: response, today=TODAY)


@pytest.mark.parametrize("slug", ["acme", "acme.wd5", "acme/Careers"])
def test_rejects_a_bad_slug(slug):
    with pytest.raises(SourceError, match="Workday slug"):
        workday.fetch_jobs(Source("Acme", "workday", slug), post=lambda url, payload: {}, today=TODAY)


def test_builds_the_api_url_from_the_slug():
    urls = []

    def post(url, payload):
        urls.append(url)
        return {"total": 0, "jobPostings": [], "facets": []}

    workday.fetch_jobs(ACME, post=post, today=TODAY)
    assert urls == ["https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"]
