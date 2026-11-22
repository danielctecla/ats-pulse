"""Load the job boards to poll from sources.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

SOURCES_FILE = Path(__file__).with_name("sources.toml")


@dataclass(frozen=True)
class Source:
    company: str
    ats: str
    slug: str

    @property
    def key(self) -> str:
        """Unique id of the board, e.g. "ashby:nubank". Part of each job's pk."""
        return f"{self.ats}:{self.slug}"


def load_sources(path: Path = SOURCES_FILE, supported_ats=None) -> list[Source]:
    """Parse and validate the config. A bad config is a deploy bug, so it raises."""
    if supported_ats is None:
        from .adapters import ADAPTERS

        supported_ats = ADAPTERS.keys()

    with open(path, "rb") as f:
        entries = tomllib.load(f).get("sources", [])

    sources = []
    for i, entry in enumerate(entries):
        missing = {"company", "ats", "slug"} - entry.keys()
        if missing:
            raise ValueError(f"sources[{i}] is missing {sorted(missing)}")
        if entry["ats"] not in supported_ats:
            raise ValueError(f"sources[{i}]: unsupported ats {entry['ats']!r}")
        sources.append(Source(entry["company"], entry["ats"], entry["slug"]))

    keys = [s.key for s in sources]
    if len(keys) != len(set(keys)):
        raise ValueError("sources.toml has duplicate ats/slug entries")
    # Each company has one health record (failure counter, alert flag), so two
    # boards of the same company need distinct names, e.g. "Acme" and "Acme MX".
    companies = [s.company for s in sources]
    if len(companies) != len(set(companies)):
        raise ValueError("sources.toml has duplicate company names")
    return sources
