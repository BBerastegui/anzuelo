import math
import os
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

_CONSOLE = Console()


def _fmt_size(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f}KB"
    return f"{n}B"


def _fmt_tokens(n):
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _detected_companions():
    from anzuelo.hook import get_companion_info
    return get_companion_info()


_COMPANION_PREFIXES = None


def _companion_prefixes():
    global _COMPANION_PREFIXES
    if _COMPANION_PREFIXES is None:
        from anzuelo.hook import detect_companion_tools
        _COMPANION_PREFIXES = set(detect_companion_tools())
    return _COMPANION_PREFIXES


TOOL_STYLES = {
    "Bash": "green",
    "Read": "blue",
    "Write": "yellow",
    "Edit": "magenta",
    "Glob": "cyan",
    "Grep": "bright_magenta",
    "ToolUse": "white",
    "unknown": "grey",
}

EVENT_STYLES = {
    "cmd": ("$", "green"),
    "api": ("~", "cyan"),
    "tool": (">", "yellow"),
    "result": ("·", "grey"),
}


def print_report(summary, events, session_id=None):
    _print_header(session_id)
    _CONSOLE.print()
    _print_summary(summary)
    _CONSOLE.print()
    _print_tools(summary)
    _print_commands(summary)
    _print_models(summary)
    _print_events(events)
    _print_footer()


def _print_header(session_id=None):
    companions = _detected_companions()
    text = Text(justify="center")
    title = "anzuelo metrics"
    if session_id:
        title = f"anzuelo session {session_id[:8]}"
    text.append(title, style="bold bright_white")
    if companions:
        text.append(" (")
        for i, (_, label) in enumerate(companions):
            if i > 0:
                text.append(", ")
            text.append(label, style="orange3")
        text.append(" enabled)", style="orange3")
    _CONSOLE.print(Panel(text, border_style="bright_cyan", padding=0))


def _print_footer():
    _CONSOLE.print(Rule(style="dim"))
    _CONSOLE.print("[dim]anzuelo report --help[/]", justify="right")
    _CONSOLE.print()


def _print_summary(s):
    w = _CONSOLE.width
    bar_w = min(w - 28, 20)

    total = s["total_events"]
    cmds = s["commands"]
    apis = s["api_calls"]
    tools = s["tool_calls"]

    _CONSOLE.print("[bold]Summary[/]")
    _CONSOLE.print(Rule(style="dim"))

    max_count = max(cmds, apis, tools, 1)

    if total > 0:
        cmp_bar = Text()
        if cmds:
            f = int((cmds / max_count) * bar_w)
            cmp_bar.append("█" * f, style="green")
        if apis:
            f = int((apis / max_count) * bar_w)
            cmp_bar.append("█" * f, style="cyan")
        if tools:
            f = int((tools / max_count) * bar_w)
            cmp_bar.append("█" * f, style="yellow")
        pad = bar_w - len(cmp_bar.plain)
        cmp_bar.append("░" * max(pad, 0), style="dim")

        _CONSOLE.print(f"  [dim]composition[/]  {cmp_bar}")
        _CONSOLE.print(
            f"  [green]●[/] {cmds} commands    "
            f"[cyan]●[/] {apis} api calls    "
            f"[yellow]●[/] {tools} tool calls"
        )
        _CONSOLE.print()

    tokens = s["total_tokens"]
    output = s["total_output_chars"]

    _CONSOLE.print(
        f"  [dim]total tokens[/]     [bold]{_fmt_tokens(tokens):>6}[/]"
        f"  [dim]total events[/]  [bold]{total}[/]"
    )
    _CONSOLE.print(
        f"  [dim]total output[/]     [bold]{_fmt_size(output):>6}[/]"
        f"  [dim]tokens/event[/]  [bold]{_fmt_tokens(tokens // total if total else 0)}[/]"
    )
    _CONSOLE.print()


def _print_tools(s, inner=None):
    tools_list = s.get("top_tools", [])
    if not tools_list:
        return

    w = _CONSOLE.width
    bar_w = min(w - 34, 25)
    max_output = max(t["total_output"] for t in tools_list) if tools_list else 1

    _CONSOLE.print("[bold]Top Tools[/]")
    _CONSOLE.print(Rule(style="dim"))

    for t in tools_list:
        name = t["name"]
        count = t["count"]
        out = t["total_output"]
        pct = out / max_output * 100 if max_output else 0
        style = TOOL_STYLES.get(name, "white")

        bar = Text()
        if max_output > 0:
            filled = int((out / max_output) * bar_w)
            filled = min(filled, bar_w)
            bar.append("█" * filled, style=style)
            bar.append("░" * (bar_w - filled), style="dim")
        else:
            bar.append("░" * bar_w, style="dim")

        size_str = _fmt_size(out)
        _CONSOLE.print(
            f"  [{style}]{name:<8}[/] {bar}  "
            f"[bold]{size_str:>7}[/]  [dim]{pct:3.0f}%[/]  ({count} calls)"
        )
    _CONSOLE.print()


def _print_commands(s, inner=None):
    cmds = s.get("top_commands", [])
    if not cmds:
        return

    w = _CONSOLE.width
    bar_w = min(w - 34, 20)
    max_count = max(c["count"] for c in cmds) if cmds else 1
    companions = _companion_prefixes()

    _CONSOLE.print("[bold]Top Commands[/]")
    _CONSOLE.print(Rule(style="dim"))

    for c in cmds:
        name = c["name"]
        cnt = c["count"]
        pct = cnt / max_count * 100 if max_count else 0
        tok = (c.get("tokens_input", 0) or 0) + (c.get("tokens_output", 0) or 0)

        prefix = next((p for p in companions if name.startswith(p + " ")), None)
        if prefix:
            display = f"{name[len(prefix) + 1:]} \U0001fa9d"
            style = "orange3"
            bar_style = "orange3"
        else:
            display = name
            style = "green"
            bar_style = "bright_green"

        bar = Text()
        if max_count > 0:
            filled = int((cnt / max_count) * bar_w)
            filled = min(filled, bar_w)
            bar.append("█" * filled, style=bar_style)
            bar.append("░" * (bar_w - filled), style="dim")
        else:
            bar.append("░" * bar_w, style="dim")

        tok_str = _fmt_tokens(tok) if tok else ""
        _CONSOLE.print(
            f"  [{style}]{display:<14}[/] {bar}  "
            f"[bold]{cnt:>3}x[/]  [dim]{pct:3.0f}%[/]  [dim]{tok_str:>7}[/]"
        )
    _CONSOLE.print()


def _print_models(s, inner=None):
    models = s.get("models", [])
    if not models:
        return

    _CONSOLE.print("[bold]Models[/]")
    _CONSOLE.print(Rule(style="dim"))

    for m in models:
        model = m["model"]
        cnt = m["count"]
        tin = m["tokens_in"]
        tout = m["tokens_out"]
        _CONSOLE.print(f"  [cyan]{model:<30}[/] [bold]{cnt}[/] calls")
        _CONSOLE.print(
            f"  {' ' * 30}  "
            f"[dim]{_fmt_tokens(tin)} in[/]  [dim]{_fmt_tokens(tout)} out[/]  "
            f"[dim]{_fmt_tokens(tin + tout)} total[/]"
        )
    _CONSOLE.print()


def _print_events(events, inner=None):
    if not events:
        return

    w = _CONSOLE.width
    _CONSOLE.print("[bold]Timeline[/]")
    _CONSOLE.print(Rule(style="dim"))

    show_count = min(len(events), max(8, (w - 40) // 3))
    show_count = min(show_count, len(events))

    for e in reversed(events[:show_count]):
        ts = e["timestamp"][11:19] if e["timestamp"] else ""
        etype = e["type"]
        icon, color = EVENT_STYLES.get(etype, ("?", "grey"))

        name = (e.get("detail") or e["name"])[:w - 25]

        extra_parts = []
        if e["output_size"]:
            extra_parts.append(f"[dim]{_fmt_size(e['output_size'])}[/]")
        if e["tokens_input"] is not None or e["tokens_output"] is not None:
            tin = e["tokens_input"] or "?"
            tout = e["tokens_output"] or "?"
            extra_parts.append(f"[dim][{tin}\u2192{tout}t][/]")
        if e["duration_ms"] is not None and e["duration_ms"] > 0:
            dur = e["duration_ms"]
            if dur >= 1000:
                extra_parts.append(f"[dim]({dur / 1000:.1f}s)[/]")
            else:
                extra_parts.append(f"[dim]({dur}ms)[/]")

        extra = " ".join(extra_parts)
        _CONSOLE.print(f"  [dim]{ts}[/] [{color}]{icon}[/] {name} {extra}")


def print_live(events, summary=None):
    w = _CONSOLE.width

    if summary:
        cmds = summary["commands"]
        tools = summary["tool_calls"]
        apis = summary["api_calls"]
        tokens = summary["total_tokens"]
        output = summary["total_output_chars"]
        total = summary["total_events"]

        tool_breakdown = ""
        top_tools = summary.get("top_tools", [])
        if top_tools:
            parts = [f"[green]{t['name']} {t['count']}[/]" for t in top_tools[:4]]
            tool_breakdown = "  " + " ".join(parts)

        _CONSOLE.print(
            f"  [bold bright_cyan]anzuelo live[/]  "
            f"[dim]{total} events[/]"
            f"  [green]{cmds} cmd[/]"
            f"  [yellow]{tools} tool[/]"
            f"  [cyan]{apis} api[/]"
            f"  [dim]{_fmt_size(output)} out[/]"
            f"  [bold]{_fmt_tokens(tokens)} tok[/]"
        )
        if tool_breakdown:
            _CONSOLE.print(f" {tool_breakdown}")
        _CONSOLE.print(Rule(style="dim"))

    for e in events:
        ts = e["timestamp"][11:19] if e["timestamp"] else ""
        etype = e["type"]
        icon, color = EVENT_STYLES.get(etype, ("?", "grey"))
        name = (e.get("detail") or e["name"])[:w - 25]

        extra_parts = []
        if e["output_size"]:
            extra_parts.append(f"[dim]{_fmt_size(e['output_size'])}[/]")
        if e["tokens_input"] is not None or e["tokens_output"] is not None:
            tin = e["tokens_input"] or "?"
            tout = e["tokens_output"] or "?"
            extra_parts.append(f"[dim][{tin}\u2192{tout}t][/]")
        if e["duration_ms"] is not None and e["duration_ms"] > 0:
            dur = e["duration_ms"]
            if dur >= 1000:
                extra_parts.append(f"[dim]({dur / 1000:.1f}s)[/]")
            else:
                extra_parts.append(f"[dim]({dur}ms)[/]")

        extra = " ".join(extra_parts)
        _CONSOLE.print(f"  [dim]{ts}[/] [{color}]{icon}[/] {name} {extra}")


def print_sessions(sessions):
    if not sessions:
        _CONSOLE.print("[dim]No sessions tracked yet[/]")
        return

    _CONSOLE.print("[bold]Sessions[/]")
    _CONSOLE.print(Rule(style="dim"))

    for s in sessions:
        sid = s["id"][:8]
        start = s["start_time"][:19] if s["start_time"] else "?"
        end = s["end_time"]
        count = s["event_count"]
        status = "[green]active[/]" if end is None else "[dim]ended[/]"

        duration = ""
        if start and end:
            try:
                s_t = datetime.fromisoformat(start)
                e_t = datetime.fromisoformat(end)
                mins = int((e_t - s_t).total_seconds() // 60)
                duration = f" [dim]({mins}m)[/]"
            except Exception:
                pass

        _CONSOLE.print(
            f"  [bright_cyan]{sid}[/]  [dim]{start}[/]{duration}"
            f"  [bold]{count}[/] events  {status}"
        )
    _CONSOLE.print()
