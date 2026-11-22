import io
import urllib.error

import pytest

from ats_pulse import fetch
from ats_pulse.fetch import SourceError

URL = "https://api.example.com/board"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(result):
    def urlopen(request, timeout):
        if isinstance(result, BaseException):
            raise result
        return FakeResponse(result)

    return urlopen


def test_returns_parsed_json(monkeypatch):
    monkeypatch.setattr(fetch.urllib.request, "urlopen", fake_urlopen(b'{"jobs": []}'))
    assert fetch.get_json(URL) == {"jobs": []}


@pytest.mark.parametrize(
    "result, message",
    [
        (urllib.error.HTTPError(URL, 503, "Service Unavailable", {}, None), "HTTP 503"),
        (TimeoutError("timed out"), "timed out"),
        (urllib.error.URLError("Name or service not known"), "Name or service not known"),
        (b"<html>maintenance</html>", "invalid JSON"),
    ],
    ids=["http-error", "timeout", "dns", "invalid-json"],
)
def test_failures_become_source_errors(monkeypatch, result, message):
    monkeypatch.setattr(fetch.urllib.request, "urlopen", fake_urlopen(result))
    with pytest.raises(SourceError, match=message):
        fetch.get_json(URL)
