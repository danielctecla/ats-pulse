import pytest

from ats_pulse.adapters import greenhouse
from ats_pulse.fetch import SourceError


def raw_by_title(payload, title):
    return next(j for j in payload["jobs"] if j["title"].strip() == title)


def test_normalizes_real_response(greenhouse_payload, lyft):
    jobs, skipped = greenhouse.parse(greenhouse_payload, lyft)

    assert len(jobs) == len(greenhouse_payload["jobs"]) == 15
    assert skipped == 0

    raw = raw_by_title(greenhouse_payload, "Android Engineer, Luxury")
    job = next(j for j in jobs if j.job_id == str(raw["id"]))
    assert job.source == "greenhouse:lyft"
    assert job.company == "Lyft"
    assert job.title == "Android Engineer, Luxury"
    assert job.location == "Mexico City, Mexico"
    assert job.department == "Software Engineering"  # from the Career Site Category field
    assert job.url == raw["absolute_url"]
    assert job.published_at == raw["first_published"]
    assert job.pk == f"job#greenhouse:lyft#{raw['id']}"


def test_strips_padded_titles(greenhouse_payload, lyft):
    jobs, _ = greenhouse.parse(greenhouse_payload, lyft)
    assert "Counsel, Patents & IP" in {j.title for j in jobs}  # " Counsel, ..." in the API


@pytest.mark.parametrize(
    "metadata, department",
    [
        (None, ""),
        ([], ""),
        ([{"name": "Other Field", "value": "Engineering"}], ""),
        ([{"name": "Career Site Category", "value": None}], ""),
        ([{"name": "Career Site Category", "value": ["Data Science", "Software Engineering"]}], "Data Science, Software Engineering"),
    ],
    ids=["none", "empty", "other-field", "null-value", "multi-select"],
)
def test_department_from_category_field(lyft, metadata, department):
    payload = {"jobs": [{"id": 1, "title": "Engineer", "metadata": metadata}]}
    [job], _ = greenhouse.parse(payload, lyft)
    assert job.department == department


def test_skips_malformed_postings(lyft):
    payload = {
        "jobs": [
            {"id": 1, "title": "Backend Engineer", "location": {"name": "Mexico City, Mexico"}},
            {"id": 2},  # no title
            {"id": 3, "title": "Engineer", "metadata": "not-a-list"},
            "not-a-job",
        ]
    }
    jobs, skipped = greenhouse.parse(payload, lyft)

    assert [j.job_id for j in jobs] == ["1"]
    assert skipped == 3


def test_rejects_unexpected_response_shape(lyft):
    with pytest.raises(SourceError):
        greenhouse.parse({"status": 404, "error": "Job not found"}, lyft)


def test_fetches_the_board_url_for_the_slug(greenhouse_payload, lyft):
    requested = []

    def fake_get(url):
        requested.append(url)
        return greenhouse_payload

    jobs, _ = greenhouse.fetch_jobs(lyft, get=fake_get)

    assert requested == ["https://boards-api.greenhouse.io/v1/boards/lyft/jobs"]
    assert len(jobs) == 15


def test_url_and_date_are_always_text(lyft):
    """The digest sorts by date and parses the URL; a non-text value must not break it."""
    payload = {"jobs": [{"id": 1, "title": "Engineer", "absolute_url": 12345, "first_published": 1732060800}]}
    [job], _ = greenhouse.parse(payload, lyft)

    assert (job.url, job.published_at) == ("12345", "1732060800")
