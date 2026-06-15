import math
import os
import shutil
import time


BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"
ORANGE = "\033[38;5;208m"

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

TOOL_COLORS = {
    "Bash": GREEN,
    "Read": BLUE,
    "Write": YELLOW,
    "Edit": MAGENTA,
    "Glob": CYAN,
    "Grep": BRIGHT_MAGENTA,
    "ToolUse": WHITE,
    "unknown": GRAY,
}

EVENT_ICONS = {
    "cmd": ("$", GREEN),
    "api": ("~", CYAN),
    "tool": (">", YELLOW),
    "result": ("·", GRAY),
}


def _term_width():
    return shutil.get_terminal_size((80, 20)).columns


def _fmt_size(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n/1_000:.1f}KB"
    return f"{n}B"


def _fmt_tokens(n):
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def _bar(value, max_value, width):
    if max_value <= 0:
        return "░" * width
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def _color_bar(value, max_value, width, color):
    if max_value <= 0:
        return f"{DIM}{'░' * width}{RESET}"
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    bar_str = "█" * filled + "░" * (width - filled)
    return f"{color}{bar_str}{RESET}"


def _color(text, color_code):
    return f"{color_code}{text}{RESET}"


def _rule(title="", char="─"):
    w = _term_width()
    if title:
        avail = w - len(title) - 4
        if avail < 4:
            return _color(f"── {title} ──", DIM)
        left = avail // 2
        right = avail - left
        return _color(f"{char * left} {title} {char * right}", DIM)
    return _color(char * w, DIM)


def print_report(summary, events, session_id=None):
    w = _term_width()
    inner = w - 4

    _print_header(w, session_id)
    print()
    _print_summary(summary, inner)
    print()
    _print_tools(summary, inner)
    _print_commands(summary, inner)
    _print_models(summary, inner)
    _print_events(events, inner)
    _print_footer(w)


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


def _print_header(w, session_id=None):
    companions = _detected_companions()
    title = " anzuelo  metrics "
    if session_id:
        short = session_id[:8]
        title = f" anzuelo  session {short} "
    if companions:
        labels = [f"{ORANGE}{label}{RESET}" for _, label in companions]
        title += f"({', '.join(labels)} {ORANGE}enabled{RESET})"
    bar = "─" * (w - 2)
    print(f"  {BOLD}{BRIGHT_CYAN}╭{bar}╮{RESET}")
    pad = (w - len(title) - 2) // 2
    print(f"  {BRIGHT_CYAN}│{RESET}{' ' * pad}{BOLD}{BRIGHT_WHITE}{title}{RESET}"
          f"{' ' * (w - 2 - pad - len(title))}{BRIGHT_CYAN}│{RESET}")
    print(f"  {BRIGHT_CYAN}╰{bar}╯{RESET}")


def _print_footer(w):
    print(f"  {DIM}{'─' * (w - 2)}{RESET}")
    hint = "anzuelo report --help"
    print(f"  {DIM}{hint:>{w - 4}}{RESET}")
    print()


def _print_summary(s, inner):
    bar_w = min(inner - 24, 20)

    total = s["total_events"]
    cmds = s["commands"]
    apis = s["api_calls"]
    tools = s["tool_calls"]

    print(f"  {BOLD}Summary{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    max_count = max(cmds, apis, tools, 1)

    if total > 0:
        cmp_bar = ""
        if cmds:
            f = int((cmds / max_count) * bar_w)
            cmp_bar += f"{GREEN}{'█' * f}{RESET}"
        if apis:
            f = int((apis / max_count) * bar_w)
            cmp_bar += f"{CYAN}{'█' * f}{RESET}"
        if tools:
            f = int((tools / max_count) * bar_w)
            cmp_bar += f"{YELLOW}{'█' * f}{RESET}"
        pad = bar_w - (int(cmds / max_count * bar_w) if cmds else 0) - (int(apis / max_count * bar_w) if apis else 0) - (int(tools / max_count * bar_w) if tools else 0)
        cmp_bar += "░" * max(pad, 0)

        p_cmds = f"{cmds/total*100:.0f}%" if total else "0%"
        p_apis = f"{apis/total*100:.0f}%" if total else "0%"
        p_tools = f"{tools/total*100:.0f}%" if total else "0%"

        print(f"  {DIM}composition{RESET}  {cmp_bar}")
        print(f"  {GREEN}●{RESET} {cmds} commands    "
              f"{CYAN}●{RESET} {apis} api calls    "
              f"{YELLOW}●{RESET} {tools} tool calls")
        print()

    tokens = s["total_tokens"]
    output = s["total_output_chars"]
    print(f"  {DIM}total tokens{RESET}     {BOLD}{_fmt_tokens(tokens)}{RESET}"
          f"{' ' * max(0, inner - 20 - len(str(tokens)))}"
          f"{DIM}total events{RESET}  {BOLD}{total}{RESET}")
    print(f"  {DIM}total output{RESET}     {BOLD}{_fmt_size(output)}{RESET}"
          f"{' ' * max(0, inner - 20 - len(_fmt_size(output)))}"
          f"{DIM}tokens/event{RESET}  {BOLD}{_fmt_tokens(tokens // total if total else 0)}{RESET}")
    print()


def _print_tools(s, inner):
    tools = s.get("top_tools", [])
    if not tools:
        return

    bar_w = min(inner - 30, 25)
    max_output = max(t["total_output"] for t in tools) if tools else 1

    print(f"  {BOLD}Top Tools{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    for t in tools:
        name = t["name"]
        count = t["count"]
        out = t["total_output"]
        pct = out / max_output * 100 if max_output else 0
        color = TOOL_COLORS.get(name, WHITE)
        bar = _color_bar(out, max_output, bar_w, color)
        label = f"{color}{name:<8}{RESET}"
        size = _fmt_size(out)
        print(f"  {label} {bar}  {BOLD}{size:>7}{RESET}  {DIM}{pct:3.0f}%{RESET}"
              f"  ({count} calls)")
    print()


def _print_commands(s, inner):
    cmds = s.get("top_commands", [])
    if not cmds:
        return

    bar_w = min(inner - 30, 20)
    max_count = max(c["count"] for c in cmds) if cmds else 1
    companions = _companion_prefixes()

    print(f"  {BOLD}Top Commands{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    for c in cmds:
        name = c["name"]
        cnt = c["count"]
        pct = cnt / max_count * 100 if max_count else 0

        prefix = next((p for p in companions if name.startswith(p + " ")), None)
        if prefix:
            display = f"{name[len(prefix)+1:]} \U0001fa9d"
            color = ORANGE
            bar_color = ORANGE
        else:
            display = name
            color = GREEN
            bar_color = BRIGHT_GREEN

        bar = _color_bar(cnt, max_count, bar_w, bar_color)
        print(f"  {color}{display:<14}{RESET} {bar}  {BOLD}{cnt}x{RESET}"
              f"  {DIM}{pct:3.0f}%{RESET}")
    print()


def _print_models(s, inner):
    models = s.get("models", [])
    if not models:
        return

    print(f"  {BOLD}Models{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    for m in models:
        model = m["model"]
        cnt = m["count"]
        tin = m["tokens_in"]
        tout = m["tokens_out"]
        print(f"  {CYAN}{model:<30}{RESET} {BOLD}{cnt}{RESET} calls")
        print(f"  {' ' * 30}  {DIM}{_fmt_tokens(tin)} in{RESET}"
              f"  {DIM}{_fmt_tokens(tout)} out{RESET}"
              f"  {DIM}{_fmt_tokens(tin + tout)} total{RESET}")
    print()


def _print_events(events, inner):
    if not events:
        return

    print(f"  {BOLD}Timeline{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    show_count = min(len(events), max(8, (_term_width() - 40) // 3))
    show_count = min(show_count, len(events))

    for e in reversed(events[:show_count]):
        ts = e["timestamp"][11:19] if e["timestamp"] else ""
        etype = e["type"]
        icon, color = EVENT_ICONS.get(etype, ("?", GRAY))

        name = (e.get("detail") or e["name"])[:inner - 25]

        extra = ""
        if e["output_size"]:
            extra = f" {DIM}{_fmt_size(e['output_size'])}{RESET}"
        if e["tokens_input"] is not None or e["tokens_output"] is not None:
            tin = e["tokens_input"] or "?"
            tout = e["tokens_output"] or "?"
            extra = f" {DIM}[{tin}→{tout}t]{RESET}"
        if e["duration_ms"] is not None and e["duration_ms"] > 0:
            dur = e["duration_ms"]
            if dur >= 1000:
                extra += f" {DIM}({dur/1000:.1f}s){RESET}"
            else:
                extra += f" {DIM}({dur}ms){RESET}"

        print(f"  {DIM}{ts}{RESET} {color}{icon}{RESET} {name}{extra}")


def print_live(events, summary=None):
    w = _term_width()
    inner = w - 4

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
            parts = [f"{GREEN}{t['name']} {t['count']}{RESET}"
                     for t in top_tools[:4]]
            tool_breakdown = f"  {' '.join(parts)}"

        print(f"  {BOLD}{BRIGHT_CYAN}anzuelo live{RESET}  "
              f"{DIM}{total} events{RESET}"
              f"  {GREEN}{cmds} cmd{RESET}"
              f"  {YELLOW}{tools} tool{RESET}"
              f"  {CYAN}{apis} api{RESET}"
              f"  {DIM}{_fmt_size(output)} out{RESET}"
              f"  {BOLD}{_fmt_tokens(tokens)} tok{RESET}", flush=True)
        if tool_breakdown:
            print(f"  {tool_breakdown}", flush=True)
        print(f"  {DIM}{'─' * inner}{RESET}", flush=True)

    for e in events:
        ts = e["timestamp"][11:19] if e["timestamp"] else ""
        etype = e["type"]
        icon, color = EVENT_ICONS.get(etype, ("?", GRAY))
        name = (e.get("detail") or e["name"])[:inner - 25]

        extra = ""
        if e["output_size"]:
            extra = f" {DIM}{_fmt_size(e['output_size'])}{RESET}"
        if e["tokens_input"] is not None or e["tokens_output"] is not None:
            tin = e["tokens_input"] or "?"
            tout = e["tokens_output"] or "?"
            extra = f" {DIM}[{tin}→{tout}t]{RESET}"
        if e["duration_ms"] is not None and e["duration_ms"] > 0:
            dur = e["duration_ms"]
            if dur >= 1000:
                extra += f" {DIM}({dur/1000:.1f}s){RESET}"
            else:
                extra += f" {DIM}({dur}ms){RESET}"

        print(f"  {DIM}{ts}{RESET} {color}{icon}{RESET} {name}{extra}", flush=True)


def print_sessions(sessions):
    if not sessions:
        print(f"  {DIM}No sessions tracked yet{RESET}")
        return

    w = _term_width()
    inner = w - 4

    print(f"  {BOLD}Sessions{RESET}")
    print(f"  {DIM}{'─' * inner}{RESET}")

    for s in sessions:
        sid = s["id"][:8]
        start = s["start_time"][:19] if s["start_time"] else "?"
        end = s["end_time"]
        count = s["event_count"]
        status = f"{GREEN}active{RESET}" if end is None else f"{DIM}ended{RESET}"

        duration = ""
        if start and end:
            try:
                from datetime import datetime
                s_t = datetime.fromisoformat(start)
                e_t = datetime.fromisoformat(end)
                mins = int((e_t - s_t).total_seconds() // 60)
                duration = f" {DIM}({mins}m){RESET}"
            except Exception:
                pass

        print(f"  {BRIGHT_CYAN}{sid}{RESET}  {DIM}{start}{RESET}{duration}"
              f"  {BOLD}{count}{RESET} events  {status}")
    print()
