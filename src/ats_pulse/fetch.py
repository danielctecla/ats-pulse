"""HTTP requests for JSON with urllib. Every failure becomes a SourceError."""

import http.client
import json
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (compatible; job-board-client/1.0)"
HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}


class SourceError(Exception):
    """A job board couldn't be read: HTTP error, timeout, or invalid response."""


def get_json(url: str, timeout: float = TIMEOUT_SECONDS):
    return _read_json(urllib.request.Request(url, headers=HEADERS), timeout)


def post_json(url: str, payload: dict, timeout: float = TIMEOUT_SECONDS):
    """For APIs that take the query as a JSON body (Workday)."""
    headers = {**HEADERS, "Content-Type": "application/json"}
    return _read_json(urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers), timeout)


def _read_json(request: urllib.request.Request, timeout: float):
    url = request.full_url
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise SourceError(f"HTTP {exc.code} from {url}") from exc
    except (OSError, http.client.HTTPException) as exc:  # URLError, timeouts, resets
        reason = getattr(exc, "reason", None) or exc
        raise SourceError(f"request to {url} failed: {reason}") from exc

    try:
        return json.loads(body)
    except ValueError as exc:
        raise SourceError(f"invalid JSON from {url}: {exc}") from exc
