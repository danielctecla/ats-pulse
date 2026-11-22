"""Which jobs to keep: located in Mexico, and engineering."""

import re

from .models import Job

# --- Mexico: any location field, the address country, or the title ----------
_MEXICO_TEXT = re.compile(r"\b(m[eé]xico|cdmx)\b", re.IGNORECASE)
_NEW_MEXICO = re.compile(r"\bnew\s+m[eé]xico\b", re.IGNORECASE)  # the US state
_MEXICO_COUNTRIES = {"mexico", "méxico", "mx", "mex"}


def _mentions_mexico(text: str) -> bool:
    return bool(text) and bool(_MEXICO_TEXT.search(_NEW_MEXICO.sub(" ", text)))


def is_mexico(job: Job) -> bool:
    if any(c.strip().lower() in _MEXICO_COUNTRIES for c in job.countries):
        return True
    return any(_mentions_mexico(t) for t in (job.location, *job.secondary_locations, job.title))


def mexico_location(job: Job) -> str:
    """Location to show: the primary one, plus the Mexican one if it's only a secondary."""
    if _mentions_mexico(job.location) or not job.secondary_locations:
        return job.location
    mexican = next((loc for loc in job.secondary_locations if _mentions_mexico(loc)), None)
    if not mexican:
        return job.location
    return f"{mexican} (also {job.location})" if job.location else mexican


# --- Engineering: department/team OR a role word in the title ----------------
# Department names vary by company ("Engineer", "Engineering", "Data Science"...),
# so match generic fragments.
_ENGINEERING_DEPARTMENT = re.compile(
    r"engineer|machine learning|data|technology|security|infrastructure", re.IGNORECASE
)
# Role words only. Bare "AI", "Data" and "Engineering" are left out on purpose:
# on real data they matched legal, design and L&D roles.
_ENGINEERING_TITLE = re.compile(
    r"\b(engineers?|developer|sre|devops|architect|tech lead|data scientist|machine learning|ml)\b",
    re.IGNORECASE,
)


def is_engineering(job: Job) -> bool:
    return bool(
        _ENGINEERING_DEPARTMENT.search(job.department)
        or _ENGINEERING_DEPARTMENT.search(job.team)
        or _ENGINEERING_TITLE.search(job.title)
    )
