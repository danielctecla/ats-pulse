from datetime import UTC, datetime

import pytest

from ats_pulse import emails
from ats_pulse.models import NewJob, SourceAlert

from conftest import make_job

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def new(**overrides) -> NewJob:
    job = make_job(**overrides)
    return NewJob(job, job.location)


def test_digest_subject_counts_jobs_and_names_companies():
    assert emails.digest([new()]).subject == "1 new engineering job in Mexico: Acme"

    jobs = [new(job_id=str(i), company=c) for i, c in enumerate("EDCBA")]
    assert emails.digest(jobs).subject == "5 new engineering jobs in Mexico: A, B, C +2 more"


def test_digest_groups_companies_a_to_z_newest_job_first():
    jobs = [
        new(job_id="1", company="Zeta", title="Old", published_at="2026-01-01"),
        new(job_id="2", company="acme", title="Older", published_at="2026-01-01"),
        new(job_id="3", company="acme", title="Newer", published_at="2026-11-01"),
    ]
    text = emails.digest(jobs).text

    assert text.index("acme (2)") < text.index("Zeta (1)")
    assert text.index("Newer") < text.index("Older")


def test_digest_text_has_details_and_link():
    text = emails.digest([new(department="", workplace_type="Hybrid", employment_type="Full-time")], NOW).text

    assert "  Ciudad de México · Hybrid · Full-time\n" in text  # empty department skipped
    assert "  Posted Nov 20 · 2 days ago\n" in text
    assert "https://jobs.example.com/acme/job-1" in text


@pytest.mark.parametrize(
    "published_at, shown",
    [
        ("2026-11-22T09:00:00+00:00", "Nov 22 · today"),
        ("2026-11-21T09:00:00-05:00", "Nov 21 · yesterday"),  # Greenhouse sends local offsets
        ("2026-11-12T10:00:00.123+00:00", "Nov 12 · 10 days ago"),
        ("2026-10-25T10:00:00+00:00", "Oct 25 · 4 weeks ago"),
        ("2025-07-19T10:00:00+00:00", "Jul 19, 2025 · 16 months ago"),
        ("2026-11-20", "Nov 20 · 2 days ago"),  # no time or offset
        ("1732060800", "1732060800"),  # not a date: shown as given
        ("", ""),
    ],
)
def test_posted_shows_date_and_age(published_at, shown):
    assert emails.posted(published_at, NOW) == shown


def test_digest_html_has_the_same_details_as_the_text():
    html = emails.digest([new(workplace_type="Remote", employment_type="Internship")], NOW).html

    labels = (f'<span style="white-space:nowrap;">{t}</span>' for t in ("Engineering", "Remote", "Internship"))
    assert ">Ciudad de México &middot; " + " &middot; ".join(labels) + "</div>" in html
    assert ">Nov 20<div" in html and ">2 days ago</div>" in html  # date column
    assert html.count('href="https://jobs.example.com/acme/job-1"') == 1  # the title


def test_digest_html_without_a_date_shows_a_dash():
    html = emails.digest([new(published_at="")], NOW).html
    assert ">&mdash;<div" in html


def test_digest_html_escapes_job_board_content():
    html = emails.digest([new(title="<script>alert(1)</script>", company="A&B", workplace_type="<b>x</b>")]).html

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_digest_html_links_only_http_urls():
    linked = emails.digest([new(url='https://example.com/job?a=1&b="x"')]).html
    assert 'href="https://example.com/job?a=1&amp;b=&quot;x&quot;"' in linked

    unsafe = emails.digest([new(url="javascript:alert(1)")]).html
    assert "javascript:" not in unsafe
    assert "Senior Software Engineer" in unsafe  # title still shown, just not linked


def test_alert_lists_each_failing_source():
    alerts = [
        SourceAlert("Acme", "ashby:acme", 2, "SourceError: HTTP 503"),
        SourceAlert("Beta", "ashby:beta", 3, "TimeoutError: timed out"),
    ]
    email = emails.alert(alerts)

    assert email.subject == "Job boards failing: Acme, Beta"
    assert email.html is None
    assert "Acme (ashby:acme)" in email.text
    assert "Failed runs in a row: 3" in email.text
    assert "TimeoutError: timed out" in email.text
    assert emails.alert(alerts[:1]).subject == "Job board failing: Acme"


def test_malformed_url_does_not_break_the_digest():
    email = emails.digest([new(url="https://[bad/job")])

    assert "Senior Software Engineer" in email.html
    assert "href" not in email.html
    assert "[bad" not in email.text


def test_text_part_skips_unsafe_urls():
    text = emails.digest([new(url="javascript:alert(1)")]).text

    assert "javascript:" not in text
    assert "Senior Software Engineer" in text


def test_alert_puts_a_multi_line_error_on_one_line():
    text = emails.alert([SourceAlert("Acme", "ashby:acme", 2, "ClientError:\n  line one\n  line two")]).text

    assert "Last error: ClientError: line one line two" in text
