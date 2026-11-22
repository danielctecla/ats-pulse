"""One adapter per ATS. Each exposes fetch_jobs(source) -> (jobs, skipped).

To support a new ATS (Greenhouse, Lever), add a module with fetch_jobs and
register it here; companies on it are then one line in sources.toml.
"""

from . import ashby

ADAPTERS = {
    "ashby": ashby.fetch_jobs,
}
