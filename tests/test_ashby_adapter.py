import pytest

from ats_pulse.adapters import ashby
from ats_pulse.fetch import SourceError


def raw_by_title(payload, title):
    return next(j for j in payload["jobs"] if j["title"].strip() == title)


def test_normalizes_real_response(ashby_payload, nubank):
    jobs, skipped = ashby.parse(ashby_payload, nubank)

    assert len(jobs) == len(ashby_payload["jobs"]) == 26
    assert skipped == 0

    raw = raw_by_title(ashby_payload, "Lead Software Engineer - Mexico City")
    job = next(j for j in jobs if j.job_id == raw["id"])
    assert job.source == "ashby:nubank"
    assert job.company == "Nubank"
    assert job.title == "Lead Software Engineer - Mexico City"
    assert job.location == "Ciudad de México"
    assert job.department == "Engineer"
    assert job.url == raw["jobUrl"]
    assert job.published_at == raw["publishedAt"]
    assert job.countries == ("Mexico",)
    assert job.pk == f"job#ashby:nubank#{raw['id']}"


def test_keeps_secondary_locations_and_their_countries(ashby_payload, nubank):
    jobs, _ = ashby.parse(ashby_payload, nubank)
    job = next(j for j in jobs if j.title == "AI Engineer, Design")

    assert job.location == "Palo Alto"
    assert "Ciudad de México" in job.secondary_locations
    assert "Mexico" in job.countries


def test_skips_unlisted_and_malformed_postings(nubank):
    payload = {
        "jobs": [
            {"id": "1", "title": "Backend Engineer", "isListed": True},
            {"id": "2", "title": "Hidden Engineer", "isListed": False},
            {"id": "3"},  # no title
            "not-a-job",
        ]
    }
    jobs, skipped = ashby.parse(payload, nubank)

    assert [j.job_id for j in jobs] == ["1"]
    assert skipped == 2


def test_rejects_unexpected_response_shape(nubank):
    with pytest.raises(SourceError):
        ashby.parse({"error": "board not found"}, nubank)


def test_fetches_the_board_url_for_the_slug(ashby_payload, nubank):
    requested = []

    def fake_get(url):
        requested.append(url)
        return ashby_payload

    jobs, _ = ashby.fetch_jobs(nubank, get=fake_get)

    assert requested == ["https://api.ashbyhq.com/posting-api/job-board/nubank"]
    assert len(jobs) == 26


def test_url_and_date_are_always_text(nubank):
    """The digest sorts by date and parses the URL; a non-text value must not break it."""
    payload = {"jobs": [{"id": "1", "title": "Engineer", "jobUrl": 12345, "publishedAt": 1732060800}]}
    [job], _ = ashby.parse(payload, nubank)

    assert (job.url, job.published_at) == ("12345", "1732060800")
