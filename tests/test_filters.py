import pytest

from ats_pulse.adapters import ashby, greenhouse, oracle, workday
from ats_pulse.filters import is_engineering, is_mexico, mexico_location

from conftest import WORKDAY_RECORDED_ON, make_job, replay, replay_get


# --- Mexico -------------------------------------------------------------------
@pytest.mark.parametrize(
    "fields",
    [
        {"location": "Ciudad de México", "countries": ()},
        {"location": "Mexico City", "countries": ()},
        {"location": "CDMX", "countries": ()},
        {"location": "Remote", "countries": ("Mexico",)},
        {"location": "São Paulo", "secondary_locations": ("Ciudad de Mexico",), "countries": ("Brazil",)},
        {"location": "Remote", "title": "Backend Engineer - México", "countries": ()},
    ],
)
def test_mexico_positive(fields):
    assert is_mexico(make_job(**fields))


@pytest.mark.parametrize(
    "fields",
    [
        {"location": "São Paulo", "countries": ("Brazil",)},
        {"location": "Albuquerque, New Mexico", "countries": ("United States",)},
        {"location": "Remote", "countries": ()},
        {"location": "Bogotá", "secondary_locations": ("Miami",), "countries": ("Colombia", "United States")},
    ],
)
def test_mexico_negative(fields):
    assert not is_mexico(make_job(**fields))


def test_mexico_location_shows_mexican_secondary():
    job = make_job(location="Palo Alto", secondary_locations=("Toronto", "Ciudad de México"))
    assert mexico_location(job) == "Ciudad de México (also Palo Alto)"
    assert mexico_location(make_job(location="Ciudad de México")) == "Ciudad de México"


# --- Engineering --------------------------------------------------------------
@pytest.mark.parametrize(
    "title, department",
    [
        ("Senior Manager - Insider Threat Defense", "Engineer"),  # department match
        ("Research Scientist", "Machine Learning"),
        ("Analytics Lead", "Data Science"),
        ("AI Engineer, Design", "Design"),  # title match
        ("Lead Machine Learning Engineer", "Candidate Pool"),
        ("Senior Data Scientist", "Risk"),
        ("SRE II", "Operations"),
        ("Frontend Developer", "Product"),
    ],
)
def test_engineering_positive(title, department):
    assert is_engineering(make_job(title=title, department=department))


@pytest.mark.parametrize(
    "title, department",
    [
        ("Senior Legal Counsel, Privacy, AI & Consumer Protection", "Enterprise Functions"),
        ("Head of Design, AI Private Banker", "Design"),
        ("Learning & Development Senior Specialist — Tech Learning (engineering)", "Enterprise Functions"),
        ("Senior Business Analyst", "Business Analyst"),
        ("Senior Staff Product Designer", "Design"),
    ],
)
def test_engineering_negative(title, department):
    assert not is_engineering(make_job(title=title, department=department))


def test_real_response_selects_expected_jobs(ashby_payload, nubank):
    """Regression check against the real fixture: the 7 jobs the rule was approved on."""
    jobs, _ = ashby.parse(ashby_payload, nubank)
    selected = {j.title for j in jobs if is_mexico(j) and is_engineering(j)}

    assert selected == {
        "Senior Software Engineer – Mexico City, Mexico (Hybrid)",
        "Lead Software Engineer - Mexico City",
        "Staff Software Engineer",
        "Lead Infrastructure Engineer — Global Office IT Physical Infra",
        "Engineering Manager - Mexico ( Hybrid)",
        "Staff Software Engineer, Product Workflow Reinvention",
        "AI Engineer, Design",
    }


def test_real_greenhouse_response_selects_expected_jobs(greenhouse_payload, lyft):
    """Same rule on the Lyft fixture: 5 jobs in Mexico, all but customer support are engineering."""
    jobs, _ = greenhouse.parse(greenhouse_payload, lyft)
    mexico = {j.title for j in jobs if is_mexico(j)}
    selected = {j.title for j in jobs if is_mexico(j) and is_engineering(j)}

    assert mexico - selected == {"Social Support Associate, Customer Care Operations"}
    assert selected == {
        "Android Engineer, Luxury",
        "Engineering Manager, Business Travel",  # only the category says engineering
        "Software Engineer Intern, Backend (Summer 2027 - Mexico)",
        "Software Engineer Intern, Frontend (Summer 2027)",
    }


def test_real_workday_response_selects_every_job(salesforce, workday_recording):
    """The Workday adapter only fetches Mexico openings in engineering categories, so all pass,
    including two analyst roles whose titles alone wouldn't."""
    jobs, _ = workday.fetch_jobs(salesforce, post=replay(workday_recording), today=WORKDAY_RECORDED_ON)

    assert all(is_mexico(j) and is_engineering(j) for j in jobs)
    assert len(jobs) == 12


def test_real_oracle_responses_select_expected_jobs(jpmorgan, jpmorgan_recording, oracle_corp, oracle_recording):
    """The Oracle adapter only fetches Mexico openings, so all pass the Mexico rule. JPMorgan's
    engineering one is matched by its job family; Oracle has no job families, so its jobs are
    matched on the title only (Spanish titles such as "Arquitecto/a" aren't)."""
    jpm, _ = oracle.fetch_jobs(jpmorgan, get=replay_get(jpmorgan_recording))
    orcl, _ = oracle.fetch_jobs(oracle_corp, get=replay_get(oracle_recording))

    assert all(is_mexico(j) for j in jpm + orcl)
    assert {j.title for j in jpm if is_engineering(j)} == {"Technology Risk & Controls Director (CISO - Cyber)"}
    assert {j.title for j in orcl if is_engineering(j)} == {
        "OIC Integration Developer",
        "GTM Specialist – Junior Developer Relations",
        "Senior Solutions Architect | Oracle Analytics & FDI",
        "Senior Site Reliability Engineer",  # 4 openings
        "Principal Application Software Engineer",  # Mexico is a secondary location
        "Cloud Architect – Retail & Multi-Industry",
        "Cloud Architect – Financial Services Industry (FSI)",
        "Principal Network Developer",
        "Senior Product Engineer – GPU Server Platforms (Ciudad Juarez, México)",
        "SRE-Cloud Engineer II",
        "SRE-Cloud Engineer II - Java",
        "Senior Data Systems Operations Developer",
    }
    assert sum(is_engineering(j) for j in orcl) == 15
