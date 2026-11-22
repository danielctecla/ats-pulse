"""HTTP GET of JSON with urllib. Every failure becomes a SourceError."""

import http.client
import json
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (compatible; job-board-client/1.0)"


class SourceError(Exception):
    """A job board couldn't be read: HTTP error, timeout, or invalid response."""


def get_json(url: str, timeout: float = TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
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
