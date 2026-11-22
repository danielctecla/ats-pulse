import json
import logging

import pytest

from ats_pulse import handler, pipeline
from ats_pulse.adapters import ADAPTERS, ashby, greenhouse
from ats_pulse.config import Source
from ats_pulse.fetch import SourceError

from conftest import EMAIL, TABLE_NAME, make_job, sent_emails

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


def test_digest_failure_saves_nothing_and_fails_the_run(store, table, notifier):
    notifier.fail_digest = True
    with pytest.raises(pipeline.NotificationError, match="digest"):
        pipeline.run([GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    saved = make_job(source="good:good", company="Good")
    assert "Item" not in table.get_item(Key={"pk": saved.pk})  # retried next run

    notifier.fail_digest = False
    assert pipeline.run([GOOD], store, notifier, adapters=ADAPTERS_MIXED)["new"] == 1


def test_failed_alert_does_not_hold_back_the_digest(store, table, notifier):
    pipeline.run([BROKEN], store, notifier, adapters=ADAPTERS_MIXED)  # 1st failure, no alert yet
    notifier.fail_alert = True

    with pytest.raises(pipeline.NotificationError, match="alert"):
        pipeline.run([BROKEN, GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    assert len(notifier.digests) == 1
    saved = make_job(source="good:good", company="Good")
    assert "Item" in table.get_item(Key={"pk": saved.pk})


def test_failed_digest_does_not_hold_back_the_alert(store, notifier):
    pipeline.run([BROKEN], store, notifier, adapters=ADAPTERS_MIXED)
    notifier.fail_digest = True

    with pytest.raises(pipeline.NotificationError, match="digest"):
        pipeline.run([BROKEN, GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    assert len(notifier.alerts) == 1


def test_failed_alert_bookkeeping_does_not_hold_back_the_digest(store, notifier, monkeypatch):
    """Alert sent, then the DynamoDB write that records it fails: the digest still goes out."""
    pipeline.run([BROKEN], store, notifier, adapters=ADAPTERS_MIXED)

    def throttled(company):
        raise RuntimeError("DynamoDB throttled")

    monkeypatch.setattr(store, "mark_alert_sent", throttled)
    with pytest.raises(RuntimeError, match="throttled"):
        pipeline.run([BROKEN, GOOD], store, notifier, adapters=ADAPTERS_MIXED)

    assert (len(notifier.alerts), len(notifier.digests)) == (1, 1)


def test_long_errors_are_cut_in_the_alert(store, notifier):
    huge = {"huge": raise_(SourceError("x" * 5000))}
    source = Source(company="Huge", ats="huge", slug="huge")
    for _ in range(2):
        pipeline.run([source], store, notifier, adapters=huge)

    assert len(notifier.alerts[0][0].last_error) == 500  # same as what DynamoDB keeps


def test_handler_runs_configured_sources(table, ses, monkeypatch, ashby_payload, greenhouse_payload):
    """End to end through lambda_handler: API calls replaced by the fixtures, SES by moto."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("NOTIFICATION_EMAIL", EMAIL)
    monkeypatch.setitem(ADAPTERS, "ashby", lambda source: ashby.parse(ashby_payload, source))
    monkeypatch.setitem(ADAPTERS, "greenhouse", lambda source: greenhouse.parse(greenhouse_payload, source))

    first = handler.lambda_handler({}, None)
    second = handler.lambda_handler({}, None)

    assert first == {"sources": 2, "failed_sources": 0, "new": 11, "alerts": 0}  # 7 + 4
    assert second["new"] == 0
    assert json.dumps(first)  # JSON-serializable for the Lambda response

    assert [m.subject for m in sent_emails()] == ["11 new engineering jobs in Mexico: Lyft, Nubank"]
