import pytest

from ats_pulse.config import load_sources


def test_rejects_duplicate_company_names(tmp_path):
    """Each company has one health record, so two boards can't share a name."""
    path = tmp_path / "sources.toml"
    path.write_text(
        '[[sources]]\ncompany = "Acme"\nats = "ashby"\nslug = "acme"\n\n'
        '[[sources]]\ncompany = "Acme"\nats = "ashby"\nslug = "acme-mx"\n'
    )
    with pytest.raises(ValueError, match="duplicate company names"):
        load_sources(path, supported_ats={"ashby"})


def test_bundled_config_is_valid():
    assert load_sources()
