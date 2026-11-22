import json
import logging

from ats_pulse import handler, pipeline
from ats_pulse.adapters import ADAPTERS, ashby
from ats_pulse.config import Source
from ats_pulse.fetch import SourceError

from conftest import TABLE_NAME, make_job

BROKEN = Source(company="Broken", ats="broken", slug="broken")
SLOW = Source(company="Slow", ats="slow", slug="slow")
GOOD = Source(company="Good", ats="good", slug="good")


def raise_(exc):
    def adapter(source):
        raise exc

    return adapter


ADAPTERS_MIXED = {
    "broken": raise_(SourceError("invalid JSON from https://api.example.com/broken")),
    "slow": raise_(TimeoutError("timed out")),
    "good": lambda source: ([make_job(source=source.key, company="Good")], 0),
}


def summary_lines(caplog):
    return {r.source: r for r in caplog.records if r.getMessage() == "source summary"}


def test_failing_sources_do_not_stop_the_others(store, table, notifier):
    summary = pipeline.run([BROKEN, SLOW, GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    assert summary == {"sources": 3, "failed_sources": 2, "new": 1, "alerts": 0}
    saved = make_job(source="good:good", company="Good")
    assert table.get_item(Key={"pk": saved.pk})["Item"]["company"] == "Good"


def test_logs_one_summary_line_per_source(store, notifier, caplog):
    caplog.set_level(logging.INFO, logger="ats_pulse")
    pipeline.run([BROKEN, SLOW, GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    lines = summary_lines(caplog)
    assert set(lines) == {"broken:broken", "slow:slow", "good:good"}

    good = lines["good:good"]
    assert (good.fetched, good.mexico, good.engineering, good.new, good.errors) == (1, 1, 1, 1, 0)
    assert lines["slow:slow"].errors == 1
    assert "TimeoutError" in lines["slow:slow"].error
    assert lines["broken:broken"].levelname == "WARNING"


def test_handler_runs_configured_sources(table, monkeypatch, ashby_payload):
    """End to end through lambda_handler, with the Ashby HTTP call replaced by the fixture."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setitem(ADAPTERS, "ashby", lambda source: ashby.parse(ashby_payload, source))

    first = handler.lambda_handler({}, None)
    second = handler.lambda_handler({}, None)

    assert first == {"sources": 1, "failed_sources": 0, "new": 7, "alerts": 0}
    assert second["new"] == 0
    assert json.dumps(first)  # JSON-serializable for the Lambda response
