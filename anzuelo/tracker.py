from anzuelo.store import Store


_store = None


def _get_store():
    global _store
    if _store is None:
        _store = Store()
    return _store


def _companion_name(cmd):
    """If cmd starts with a known companion tool prefix, use first two words."""
    from anzuelo.hook import detect_companion_tools
    tools = detect_companion_tools()
    if tools and cmd:
        parts = cmd.split()
        first = parts[0]
        if first in tools and len(parts) > 1:
            return f"{first} {parts[1]}"
    return cmd.split()[0] if cmd else cmd


def log_command(cmd, exit_code=None, duration_ms=None, output_size=None, session_id=None):
    name = _companion_name(cmd)
    return _get_store().log_event(
        type="cmd", name=name, detail=cmd,
        exit_code=exit_code, duration_ms=duration_ms,
        output_size=output_size, session_id=session_id,
    )


def log_api_call(model, tokens_input=None, tokens_output=None, endpoint="", session_id=None):
    return _get_store().log_event(
        type="api", name=endpoint, detail=model or "",
        tokens_input=tokens_input, tokens_output=tokens_output,
        model=model, session_id=session_id,
    )


def log_tool_call(tool_name, detail="", exit_code=None, output_size=None, session_id=None):
    return _get_store().log_event(
        type="tool", name=tool_name, detail=detail,
        exit_code=exit_code, output_size=output_size,
        session_id=session_id,
    )


def log_result(tool_name, exit_code=None, output_size=None, session_id=None):
    return _get_store().log_event(
        type="result", name=tool_name,
        exit_code=exit_code, output_size=output_size,
        session_id=session_id,
    )


def get_summary(session_id=None):
    return _get_store().get_summary(session_id=session_id)


def get_sessions():
    return _get_store().get_sessions()


def get_events(**kwargs):
    return _get_store().get_events(**kwargs)


def get_live(after_id=0, session_id=None):
    return _get_store().get_live(after_id=after_id, session_id=session_id)


def reset(session_id=None):
    _get_store().clear(session_id=session_id)
