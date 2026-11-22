from ats_pulse import pipeline
from ats_pulse.config import Source
from ats_pulse.fetch import SourceError

from conftest import make_job

ACME = Source(company="Acme", ats="fake", slug="acme")


def failing(source):
    raise SourceError("HTTP 503 from https://api.example.com/acme")


def working(source):
    return [make_job()], 0


def health(table):
    return table.get_item(Key={"pk": "health#Acme"})["Item"]


def run(store, notifier, adapter):
    return pipeline.run([ACME], store, notifier, adapters={"fake": adapter})


def test_failure_increments_counter_and_records_error(store, table, notifier):
    run(store, notifier, failing)
    assert health(table)["consecutive_failures"] == 1
    assert "HTTP 503" in health(table)["last_error"]

    run(store, notifier, failing)
    assert health(table)["consecutive_failures"] == 2


def test_success_resets_counter(store, table, notifier):
    run(store, notifier, failing)
    run(store, notifier, working)

    item = health(table)
    assert item["consecutive_failures"] == 0
    assert item["last_success_at"]


def test_alert_sent_exactly_once_at_two_failures(store, notifier):
    run(store, notifier, failing)
    assert notifier.alerts == []  # one failure: no alert yet

    run(store, notifier, failing)
    assert len(notifier.alerts) == 1
    alert = notifier.alerts[0][0]
    assert (alert.company, alert.source, alert.consecutive_failures) == ("Acme", "fake:acme", 2)
    assert "HTTP 503" in alert.last_error

    run(store, notifier, failing)
    run(store, notifier, failing)
    assert len(notifier.alerts) == 1  # still failing: not repeated


def test_alert_rearms_after_recovery(store, notifier):
    for adapter in (failing, failing, working, failing, failing):
        run(store, notifier, adapter)

    assert len(notifier.alerts) == 2
