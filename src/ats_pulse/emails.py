"""Email content: the job digest (HTML plus a plain-text part) and the source alert.

Pure functions, so they can be tested and previewed without AWS
(make run-local writes the digest to preview.html). Every value that comes from
a job board is HTML-escaped, and only http(s) links are rendered.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from itertools import groupby
from urllib.parse import urlsplit

from .models import NewJob, SourceAlert

FOOTER = "Sent by ats-pulse. Only openings not seen in earlier runs."
CREDIT_NAME, CREDIT_URL = "danielctecla", "https://www.linkedin.com/in/danielctecla/"


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str | None = None


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def name_list(names: list[str], limit: int = 3) -> str:
    """"A", "A and B", "A, B and C", "A, B, C and 2 more": a subject line stays short."""
    if len(names) > limit + 1:  # "and 1 more" would be as long as the name
        return f"{', '.join(names[:limit])} and {len(names) - limit} more"
    return " and ".join(filter(None, [", ".join(names[:-1]), names[-1]])) if names else ""


# --- digest -----------------------------------------------------------------


def by_company(new_jobs: list[NewJob]) -> list[tuple[str, list[NewJob]]]:
    """Companies A-Z; within each, newest posting first."""
    newest_first = sorted(new_jobs, key=lambda n: (n.job.published_at, n.job.title), reverse=True)
    ordered = sorted(newest_first, key=lambda n: (n.job.company.casefold(), n.job.company))  # stable
    return [(company, list(jobs)) for company, jobs in groupby(ordered, key=lambda n: n.job.company)]


def tags(n: NewJob) -> list[str]:
    """Department, workplace and employment type, skipping the ones the ATS didn't give."""
    return [t for t in (n.job.department, n.job.workplace_type, n.job.employment_type) if t]


def age(days: int) -> str:
    if days < 1:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def posting_date(published_at: str, now: datetime) -> tuple[str, str]:
    """('Nov 19', '2 days ago'). A date that doesn't parse is shown as given (first 10 chars), with no age."""
    try:
        when = datetime.fromisoformat(published_at)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        # Calendar days in the posting's own timezone, so the age matches the date shown
        days = (now.astimezone(when.tzinfo).date() - when.date()).days
    except (TypeError, ValueError, OverflowError):
        return published_at[:10], ""
    year = f", {when.year}" if when.year != now.year else ""
    return f"{when:%b} {when.day}{year}", age(days)


def posted(published_at: str, now: datetime) -> str:
    """'Nov 19 · 2 days ago', or '' when the ATS gave no date."""
    return " · ".join(part for part in posting_date(published_at, now) if part)


def safe_url(url: str) -> str | None:
    """Only http(s) links make it into the email (no javascript:, data:, ...).

    Never raises: one malformed URL must not block the whole digest.
    """
    try:
        return url if urlsplit(url).scheme in ("http", "https") else None
    except ValueError:  # e.g. "https://[bad/job" (invalid IPv6 host)
        return None


def digest(new_jobs: list[NewJob], now: datetime | None = None, logos: dict[str, str] | None = None) -> Email:
    """logos: company -> image URL, shown in the HTML instead of the company name."""
    now = now or datetime.now(UTC)
    groups = by_company(new_jobs)
    heading = f"{plural(len(new_jobs), 'new engineering job')} in Mexico"
    # Short and plain: the count goes in the inbox preview (preheader), not here
    subject = f"Openings at {name_list([company for company, _ in groups])}"
    return Email(subject, digest_text(heading, groups, now), digest_html(heading, groups, now, logos or {}))


def about(n: NewJob) -> str:
    """'Mexico City · Software Engineering · Hybrid': where, plus whatever the ATS says about the role."""
    return " · ".join(part for part in (n.location, *tags(n)) if part)


def digest_text(heading: str, groups: list[tuple[str, list[NewJob]]], now: datetime) -> str:
    lines = [heading]
    for company, jobs in groups:
        lines += ["", f"{company} ({len(jobs)})"]
        for n in jobs:
            lines += ["", f"  {n.job.title}"]
            if line := about(n):
                lines.append(f"  {line}")
            if when := posted(n.job.published_at, now):
                lines.append(f"  Posted {when}")
            if url := safe_url(n.job.url):
                lines.append(f"  {url}")
    lines += ["", "--", FOOTER, f"Built by {CREDIT_NAME}: {CREDIT_URL}"]
    return "\n".join(lines) + "\n"


# Email clients ignore <style> blocks and most modern CSS, so the layout is
# tables with inline styles, max 560px wide. A listing, like a logbook: the
# posting date in its own column, a heavy rule over each company, hairlines
# between jobs. Black and grays only, plus the red dot in the wordmark. Light
# only: the color-scheme meta keeps clients that honor it from inverting it.
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
INK, GRAY, HAIRLINE, WATERMARK, RED = "#111111", "#737373", "#e5e5e5", "#eeeeee", "#e5484d"
TABLE = 'role="presentation" width="100%" cellpadding="0" cellspacing="0"'

DIGEST_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{heading}</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;">
<div style="display:none;max-height:0;overflow:hidden;">{preheader}</div>
<table {table} style="background:#ffffff;">
<tr><td style="padding:36px 20px;">
<table {table} style="max-width:560px;font-family:{font};color:{ink};">
<tr><td style="font-size:26px;line-height:1.2;font-weight:700;letter-spacing:-0.02em;">{heading}</td></tr>
<tr><td style="padding-top:8px;font-size:14px;line-height:1.5;color:{gray};">{summary}</td></tr>
{sections}
<tr><td style="padding-top:44px;font-size:12px;line-height:1.5;color:{gray};">{footer}</td></tr>
<tr><td style="padding-top:2px;font-size:64px;line-height:1;font-weight:800;letter-spacing:-0.05em;color:{watermark};">ats-pulse<span style="color:{red};">.</span></td></tr>
<tr><td style="padding-top:10px;font-size:12px;line-height:1.5;color:{gray};">Built by <a href="{credit_url}" style="color:{ink};text-decoration:underline;">{credit_name}</a></td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""

SECTION_HTML = """<tr><td style="padding-top:40px;">
<table {table}><tr>
<td valign="bottom" style="padding-bottom:8px;border-bottom:2px solid {ink};font-size:17px;line-height:1.2;font-weight:700;">{company}</td>
<td align="right" valign="bottom" style="padding-bottom:8px;border-bottom:2px solid {ink};font-size:14px;color:{gray};">{count}</td>
</tr></table>
</td></tr>
{jobs}"""

JOB_HTML = """<tr><td style="border-bottom:1px solid {hairline};">
<table {table}><tr>
<td width="92" valign="top" style="width:92px;padding:14px 12px 14px 0;font-size:13px;line-height:1.45;color:{ink};">{date}<div style="font-size:12px;color:{gray};">{age}</div></td>
<td valign="top" style="padding:14px 0;">
<div style="font-size:15px;line-height:1.4;font-weight:600;">{title}</div>
<div style="padding-top:2px;font-size:13px;line-height:1.45;color:{gray};">{about}</div>
</td>
</tr></table>
</td></tr>"""

LINK_HTML = '<a href="{url}" style="color:{ink};text-decoration:none;">{title}</a>'
# Height only: each logo keeps its own proportions. If images are blocked, the alt shows the name.
LOGO_HTML = '<img src="{url}" alt="{company}" height="28" style="display:block;height:28px;border:0;">'


def job_html(n: NewJob, now: datetime) -> str:
    title = escape(n.job.title)
    if url := safe_url(n.job.url):
        title = LINK_HTML.format(url=escape(url, quote=True), title=title, ink=INK)
    date, job_age = posting_date(n.job.published_at, now)
    return JOB_HTML.format(
        table=TABLE,
        hairline=HAIRLINE,
        ink=INK,
        gray=GRAY,
        date=escape(date) or "&mdash;",
        age=escape(job_age),
        title=title,
        about=about_html(n),
    )


def about_html(n: NewJob) -> str:
    """Like about(), but short labels such as "Full-time" never break across lines."""
    labels = [f'<span style="white-space:nowrap;">{escape(t)}</span>' for t in tags(n)]
    return " &middot; ".join([escape(n.location)] * bool(n.location) + labels)


def company_html(company: str, logo: str | None) -> str:
    if logo and (url := safe_url(logo)):
        return LOGO_HTML.format(url=escape(url, quote=True), company=escape(company, quote=True))
    return escape(company)


def digest_html(heading: str, groups: list[tuple[str, list[NewJob]]], now: datetime, logos: dict[str, str]) -> str:
    sections = [
        SECTION_HTML.format(
            table=TABLE,
            ink=INK,
            gray=GRAY,
            company=company_html(company, logos.get(company)),
            count=len(jobs),
            jobs="\n".join(job_html(n, now) for n in jobs),
        )
        for company, jobs in groups
    ]
    summary = " · ".join(f"{company} {len(jobs)}" for company, jobs in groups)
    # Inbox preview, shown after the subject instead of the first words of the body
    preheader = f"{plural(sum(len(jobs) for _, jobs in groups), 'engineering opening')} in Mexico"
    return DIGEST_HTML.format(
        heading=escape(heading),
        summary=escape(summary),
        preheader=escape(preheader),
        sections="\n".join(sections),
        footer=escape(FOOTER),
        table=TABLE,
        font=FONT,
        ink=INK,
        gray=GRAY,
        watermark=WATERMARK,
        red=RED,
        credit_name=escape(CREDIT_NAME),
        credit_url=escape(CREDIT_URL, quote=True),
    )


# --- alert (plain text) -----------------------------------------------------


def alert(alerts: list[SourceAlert]) -> Email:
    names = [a.company for a in alerts]
    subject = f"Job board{'' if len(alerts) == 1 else 's'} failing: {name_list(names)}"
    lines = ["These job boards keep failing, so their openings aren't being checked:"]
    for a in alerts:
        lines += [
            "",
            f"- {a.company} ({a.source})",
            f"  Failed runs in a row: {a.consecutive_failures}",
            f"  Last error: {' '.join(a.last_error.split())}",  # one line, even for multi-line errors
        ]
    lines += [
        "",
        "The other sources keep running. You won't get another alert for a board",
        "until it recovers and then fails again. Details are in the Lambda's CloudWatch logs.",
    ]
    return Email(subject, "\n".join(lines) + "\n")

