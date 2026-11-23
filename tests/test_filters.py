import pytest

from ats_pulse.adapters import ashby, greenhouse, workday
from ats_pulse.filters import is_engineering, is_mexico, mexico_location

from conftest import WORKDAY_RECORDED_ON, make_job, replay


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
