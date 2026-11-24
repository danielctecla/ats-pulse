import pytest

from ats_pulse.adapters import oracle
from ats_pulse.config import Source
from ats_pulse.fetch import SourceError

from conftest import replay_get

ACME = Source(company="Acme", ats="oracle", slug="acme.fa.us2/CX_1")


def requisition(n, title="Software Engineer", **fields):
    return {
        "Id": str(n),
        "Title": title,
        "PrimaryLocation": "Ciudad De Mexico, Mexico",
        "PrimaryLocationCountry": "MX",
        "PostedDate": "2026-11-20",
        "secondaryLocations": [],
        **fields,
    }


def page(requisitions, total):
    return {"items": [{"TotalJobsCount": total, "requisitionList": requisitions}], "count": 1, "hasMore": False}


def fake_board(requisitions):
    """Pages like the real API: 25 at a time, the total on every page. Returns (get, offsets)."""
    offsets = []

    def get(url):
        assert "siteNumber=CX_1," in url and "location=Mexico" in url
        offset = int(url.rsplit("offset=", 1)[1])
        offsets.append(offset)
        return page(requisitions[offset : offset + oracle.PAGE_SIZE], len(requisitions))

    return get, offsets


def test_normalizes_real_board_with_job_families(jpmorgan, jpmorgan_recording):
    jobs, skipped = oracle.fetch_jobs(jpmorgan, get=replay_get(jpmorgan_recording))

    assert (len(jobs), skipped) == (17, 0)
    job = next(j for j in jobs if j.job_id == "210758198")
    assert job.title == "Technology Risk & Controls Director (CISO - Cyber)"
    assert job.location == "Ciudad De Mexico, Mexico"
    assert job.department == "Technology Risk & Services"  # the job family
    assert job.countries == ("MX",)
    assert job.url == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210758198"
    assert job.published_at == "2026-07-07"
    assert job.pk == "job#oracle:jpmc.fa/CX_1001#210758198"


def test_pages_through_real_board_without_job_families(oracle_corp, oracle_recording):
    jobs, skipped = oracle.fetch_jobs(oracle_corp, get=replay_get(oracle_recording))

    assert (len(jobs), skipped) == (28, 0)  # 25 + 3
    assert all(j.department == "" for j in jobs)

    job = next(j for j in jobs if j.job_id == "347625")
    assert job.title == "Principal Application Software Engineer"
    assert job.location == "India"
    assert job.secondary_locations == ("Mexico",)  # returned because Mexico is a secondary location
    assert job.countries == ("IN", "MX")
    assert job.url == "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/jobsearch/job/347625"


def test_pages_through_all_results():
    get, offsets = fake_board([requisition(n) for n in range(60)])

    jobs, _ = oracle.fetch_jobs(ACME, get=get)

    assert len(jobs) == 60
    assert offsets == [0, 25, 50]


def test_keeps_one_copy_of_a_job_pushed_to_the_next_page():
    """A job posted between two requests shifts the list: page 2 starts with page 1's last job."""
    requisitions = [requisition(n) for n in range(30)]
    pages = {"0": page(requisitions[:25], 30), "25": page(requisitions[24:], 31)}

    jobs, _ = oracle.fetch_jobs(ACME, get=lambda url: pages[url.rsplit("offset=", 1)[1]])

    assert sorted(int(j.job_id) for j in jobs) == list(range(30))


def test_stops_at_an_empty_page():
    requests = []

    def get(url):
        requests.append(url)
        return page([requisition(n) for n in range(25)] if len(requests) == 1 else [], 100)

    jobs, _ = oracle.fetch_jobs(ACME, get=get)

    assert (len(jobs), len(requests)) == (25, 2)


def test_skips_malformed_requisitions():
    get, _ = fake_board(
        [requisition(1), {"Id": "2"}, requisition(3, title="  "), requisition(""), requisition(5, title=None)]
    )

    jobs, skipped = oracle.fetch_jobs(ACME, get=get)

    assert ([j.job_id for j in jobs], skipped) == (["1"], 4)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"items": []},
        {"items": [None]},
        {"items": [{"TotalJobsCount": 3}]},
        {"items": [{"requisitionList": []}]},
    ],
)
def test_unexpected_response_raises(payload):
    with pytest.raises(SourceError, match="unexpected Oracle response"):
        oracle.fetch_jobs(ACME, get=lambda url: payload)


@pytest.mark.parametrize("slug", ["acme", "acme.fa.us2", "acme/CX_1", "acme.fa/"])
def test_rejects_malformed_slug(slug):
    with pytest.raises(SourceError, match="<pod>/<site>"):
        oracle.fetch_jobs(Source(company="Acme", ats="oracle", slug=slug), get=lambda url: page([], 0))
