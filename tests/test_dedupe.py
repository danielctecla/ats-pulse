from ats_pulse import pipeline
from ats_pulse.config import Source

from conftest import make_job

ACME = Source(company="Acme", ats="fake", slug="acme")
STORED_FIELDS = {
    "pk", "job_id", "source", "company", "title", "location",
    "department", "url", "published_at", "first_seen_at",
}


def adapters_returning(jobs):
    return {"fake": lambda source: (jobs, 0)}


def test_saves_new_job_and_skips_one_already_in_table(store, table, notifier):
    old = make_job(job_id="old")
    new = make_job(job_id="new", title="Data Engineer")
    store.save_job(old, old.location, "2026-01-01T00:00:00+00:00")

    summary = pipeline.run([ACME], store, notifier, adapters=adapters_returning([old, new]))

    assert summary["new"] == 1
    assert [n.job.job_id for n in notifier.digests[0]] == ["new"]
    assert table.get_item(Key={"pk": new.pk})["Item"]["title"] == "Data Engineer"
    # The existing job wasn't rewritten
    assert table.get_item(Key={"pk": old.pk})["Item"]["first_seen_at"] == "2026-01-01T00:00:00+00:00"


def test_second_run_with_same_jobs_finds_nothing_new(store, notifier):
    adapters = adapters_returning([make_job(job_id="a"), make_job(job_id="b")])

    assert pipeline.run([ACME], store, notifier, adapters=adapters)["new"] == 2
    assert pipeline.run([ACME], store, notifier, adapters=adapters)["new"] == 0
    assert len(notifier.digests) == 1  # nothing to send the second time


def test_stores_only_the_summary_fields(store, table, notifier):
    job = make_job()
    pipeline.run([ACME], store, notifier, adapters=adapters_returning([job]))

    item = table.get_item(Key={"pk": job.pk})["Item"]
    assert set(item) == STORED_FIELDS
    assert item["pk"] == "job#ashby:acme#job-1"


def test_existing_pks_handles_more_than_one_batch(store):
    jobs = [make_job(job_id=str(i)) for i in range(150)]
    for job in jobs[::2]:  # store every other one
        store.save_job(job, job.location, "2026-01-01T00:00:00+00:00")

    found = store.existing_pks([j.pk for j in jobs])

    assert found == {j.pk for j in jobs[::2]}
