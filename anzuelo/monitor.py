import json
import os
import sys


PATCHED = False


def install_hooks():
    global PATCHED
    if PATCHED:
        return
    if not os.environ.get("ANZUELO_ACTIVE"):
        return
    _patch_requests()
    _patch_httpx()
    PATCHED = True


def _patch_requests():
    try:
        import requests
    except ImportError:
        return

    _send = requests.Session.send

    def _patched_send(self, request, **kwargs):
        resp = _send(self, request, **kwargs)
        _try_extract_tokens(request, resp)
        return resp

    requests.Session.send = _patched_send


def _patch_httpx():
    try:
        import httpx
    except ImportError:
        return

    _send = httpx.Client.send

    def _patched_send(self, request, **kwargs):
        resp = _send(self, request, **kwargs)
        _try_extract_tokens_httpx(request, resp)
        return resp

    httpx.Client.send = _patched_send


def _try_extract_tokens(request, response):
    try:
        data = response.json()
    except (ValueError, AttributeError):
        return

    usage = data.get("usage")
    if not isinstance(usage, dict):
        return

    from anzuelo.tracker import log_api_call

    in_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    out_tokens = usage.get("completion_tokens") or usage.get("output_tokens")

    if in_tokens is None and out_tokens is None:
        total = usage.get("total_tokens")
        if total is not None:
            in_tokens = total
        else:
            return

    model = data.get("model") or data.get("model_id", "unknown")
    log_api_call(model, in_tokens, out_tokens, request.url or "")


def _try_extract_tokens_httpx(request, response):
    try:
        data = response.json()
    except (ValueError, AttributeError):
        return

    usage = data.get("usage")
    if not isinstance(usage, dict):
        return

    from anzuelo.tracker import log_api_call

    in_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    out_tokens = usage.get("completion_tokens") or usage.get("output_tokens")

    if in_tokens is None and out_tokens is None:
        total = usage.get("total_tokens")
        if total is not None:
            in_tokens = total
        else:
            return

    model = data.get("model") or data.get("model_id", "unknown")
    log_api_call(model, in_tokens, out_tokens, str(request.url) if request.url else "")


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
