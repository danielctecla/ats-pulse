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


def write(tmp_path, extra):
    path = tmp_path / "sources.toml"
    path.write_text(f'[[sources]]\ncompany = "Acme"\nats = "ashby"\nslug = "acme"\n{extra}')
    return path


def test_logo_is_optional(tmp_path):
    [source] = load_sources(write(tmp_path, ""), supported_ats={"ashby"})
    assert source.logo == ""

    [source] = load_sources(write(tmp_path, 'logo = "https://example.com/acme.png"\n'), supported_ats={"ashby"})
    assert source.logo == "https://example.com/acme.png"


@pytest.mark.parametrize("logo", ['"http://example.com/acme.png"', '"acme.png"', "42"])
def test_rejects_a_logo_that_is_not_an_https_url(tmp_path, logo):
    with pytest.raises(ValueError, match="logo must be an https URL"):
        load_sources(write(tmp_path, f"logo = {logo}\n"), supported_ats={"ashby"})


def test_bundled_logos_are_set():
    assert all(s.logo for s in load_sources())
