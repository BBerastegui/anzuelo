import json
import os
import sys
import threading
from typing import Any, Dict, Optional

from anzuelo.scrub import get_scrubber

PATCHED = False
_scrub_mappings: Dict[int, Dict[str, str]] = {}
_scrub_lock = threading.Lock()
_SCRUB_ENABLED = False


def _patch_requests():
    try:
        import requests
    except ImportError:
        return

    original_send = requests.Session.send

    def patched_send(self, request, **kwargs):
        if not _SCRUB_ENABLED:
            return original_send(self, request, **kwargs)

        scrubber = get_scrubber()
        host = request.url or ""

        if scrubber.should_scrub_host(host) and request.body:
            try:
                body = request.body
                if isinstance(body, bytes):
                    body = body.decode("utf-8")
                payload = json.loads(body)
                scrubbed, mapping = scrubber.scrub_dict(payload)
                if mapping:
                    req_id = id(request)
                    with _scrub_lock:
                        _scrub_mappings[req_id] = mapping
                    new_body = json.dumps(scrubbed)
                    request.body = new_body.encode("utf-8") if isinstance(body, bytes) else new_body
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
                pass

        response = original_send(self, request, **kwargs)

        req_id = id(request)
        with _scrub_lock:
            mapping = _scrub_mappings.pop(req_id, {})

        if mapping and response.text:
            try:
                payload = json.loads(response.text)
                unscrubbed = scrubber.unscrub_dict(payload, mapping)
                response._content = json.dumps(unscrubbed).encode("utf-8")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        return response

    requests.Session.send = patched_send


def _patch_httpx():
    try:
        import httpx
    except ImportError:
        return

    original_send = httpx.Client.send

    def patched_send(self, request, **kwargs):
        if not _SCRUB_ENABLED:
            return original_send(self, request, **kwargs)

        scrubber = get_scrubber()
        host = str(request.url) if request.url else ""

        if scrubber.should_scrub_host(host) and request.content:
            try:
                body = request.content
                if isinstance(body, bytes):
                    body = body.decode("utf-8")
                payload = json.loads(body)
                scrubbed, mapping = scrubber.scrub_dict(payload)
                if mapping:
                    req_id = id(request)
                    with _scrub_lock:
                        _scrub_mappings[req_id] = mapping
                    request._content = json.dumps(scrubbed).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
                pass

        response = original_send(self, request, **kwargs)

        req_id = id(request)
        with _scrub_lock:
            mapping = _scrub_mappings.pop(req_id, {})

        if mapping and hasattr(response, "text"):
            try:
                payload = json.loads(response.text)
                unscrubbed = scrubber.unscrub_dict(payload, mapping)
                response._content = json.dumps(unscrubbed).encode("utf-8")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        return response

    httpx.Client.send = patched_send


def install_hooks():
    global PATCHED
    if PATCHED:
        return
    PATCHED = True
    _patch_requests()
    _patch_httpx()


def enable_scrub():
    global _SCRUB_ENABLED
    _SCRUB_ENABLED = True
    install_hooks()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import runpy
        target = sys.argv[1]
        sys.argv = sys.argv[1:]
        runpy.run_path(target, run_name="__main__")
    else:
        print("anzuelo monitor: no target script specified", file=sys.stderr)
        sys.exit(1)
