"""Email content: the job digest (HTML plus a plain-text part) and the source alert.

Pure functions, so they can be tested and previewed without AWS
(make run-local writes the digest to preview.html). Every value that comes from
a job board is HTML-escaped, and only http(s) links are rendered.
"""

from dataclasses import dataclass
from html import escape
from itertools import groupby
from urllib.parse import urlsplit

from .models import NewJob, SourceAlert

FOOTER = "Sent by ats-pulse. Only openings not seen in earlier runs."


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str | None = None


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def name_list(names: list[str], limit: int = 3) -> str:
    """"A, B, C +2 more" so a subject line stays short."""
    shown = ", ".join(names[:limit])
    return f"{shown} +{len(names) - limit} more" if len(names) > limit else shown


# --- digest -----------------------------------------------------------------


def by_company(new_jobs: list[NewJob]) -> list[tuple[str, list[NewJob]]]:
    """Companies A-Z; within each, newest posting first."""
    newest_first = sorted(new_jobs, key=lambda n: (n.job.published_at, n.job.title), reverse=True)
    ordered = sorted(newest_first, key=lambda n: (n.job.company.casefold(), n.job.company))  # stable
    return [(company, list(jobs)) for company, jobs in groupby(ordered, key=lambda n: n.job.company)]


def job_details(n: NewJob) -> str:
    """'Ciudad de México · Engineering · posted 2026-11-20', skipping empty parts."""
    posted = f"posted {n.job.published_at[:10]}" if n.job.published_at else ""
    return " · ".join(part for part in (n.location, n.job.department, posted) if part)


def safe_url(url: str) -> str | None:
    """Only http(s) links make it into the email (no javascript:, data:, ...).

    Never raises: one malformed URL must not block the whole digest.
    """
    try:
        return url if urlsplit(url).scheme in ("http", "https") else None
    except ValueError:  # e.g. "https://[bad/job" (invalid IPv6 host)
        return None


def digest(new_jobs: list[NewJob]) -> Email:
    groups = by_company(new_jobs)
    heading = f"{plural(len(new_jobs), 'new engineering job')} in Mexico"
    subject = f"{heading}: {name_list([company for company, _ in groups])}"
    return Email(subject, digest_text(heading, groups), digest_html(heading, groups))


def digest_text(heading: str, groups: list[tuple[str, list[NewJob]]]) -> str:
    lines = [heading]
    for company, jobs in groups:
        lines += ["", f"{company} ({len(jobs)})"]
        for n in jobs:
            lines += ["", f"  {n.job.title}", f"  {job_details(n)}"]
            if url := safe_url(n.job.url):
                lines.append(f"  {url}")
    lines += ["", "--", FOOTER]
    return "\n".join(lines) + "\n"


# Email clients ignore <style> blocks and most modern CSS, so the layout is
# tables with inline styles, max 600px wide.
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MUTED = "#6b7280"

DIGEST_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:8px;font-family:{font};color:#111827;">
<tr><td style="padding:24px 24px 4px;">
<div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:{muted};">ats-pulse</div>
<h1 style="margin:4px 0 0;font-size:20px;line-height:1.3;font-weight:700;">{heading}</h1>
</td></tr>
{sections}
<tr><td style="padding:20px 24px 24px;font-size:12px;line-height:1.5;color:{muted};">{footer}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""

SECTION_HTML = """<tr><td style="padding:20px 24px 0;">
<h2 style="margin:0 0 4px;font-size:15px;font-weight:700;">{company} <span style="font-weight:400;color:{muted};">({count})</span></h2>
{jobs}
</td></tr>"""

JOB_HTML = """<div style="padding:10px 0;border-top:1px solid #e5e7eb;">
<div style="font-size:15px;line-height:1.4;font-weight:600;">{title}</div>
<div style="margin-top:2px;font-size:13px;line-height:1.4;color:#4b5563;">{details}</div>
</div>"""

LINK_HTML = '<a href="{url}" style="color:#1d4ed8;text-decoration:none;">{title}</a>'


def digest_html(heading: str, groups: list[tuple[str, list[NewJob]]]) -> str:
    sections = []
    for company, jobs in groups:
        rendered = []
        for n in jobs:
            title = escape(n.job.title)
            url = safe_url(n.job.url)
            if url:
                title = LINK_HTML.format(url=escape(url, quote=True), title=title)
            rendered.append(JOB_HTML.format(title=title, details=escape(job_details(n))))
        sections.append(
            SECTION_HTML.format(company=escape(company), count=len(jobs), muted=MUTED, jobs="\n".join(rendered))
        )
    return DIGEST_HTML.format(
        heading=escape(heading), sections="\n".join(sections), footer=escape(FOOTER), font=FONT, muted=MUTED
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

