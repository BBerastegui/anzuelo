import argparse
import os
import subprocess
import sys
import time


def _log_run(cmd_args, exit_code, duration_ms):
    from anzuelo.tracker import log_command
    log_command(" ".join(cmd_args), exit_code, duration_ms)


def cmd_init(args):
    from anzuelo.hook import (
        get_init_script, detect_shell, install_hooks, detect_harnesses,
    )

    harness_flags = {
        "claude": getattr(args, "claude", False),
        "opencode": getattr(args, "opencode", False),
        "codex": getattr(args, "codex", False),
        "agy": getattr(args, "agy", False),
    }

    targets = []
    if getattr(args, "all_harnesses", False):
        targets = detect_harnesses()
        if not targets:
            print("  no supported AI coding harnesses detected")
            print(f"  detected dirs: claude={os.path.exists(os.path.expanduser('~/.claude'))}, opencode={os.path.exists(os.path.expanduser('~/.config/opencode'))}, codex={os.path.exists(os.path.expanduser('~/.codex'))}, agy={os.path.exists(os.path.expanduser('~/.gemini'))}")
            return
    else:
        for name, active in harness_flags.items():
            if active:
                targets.append(name)

    if targets:
        for name in targets:
            print(f"  installing anzuelo hooks for {name}...")
            install_hooks(name)
            print()
        return

    if args.global_install:
        _init_global(args)
        return
    shell = args.shell if args.shell != "auto" else detect_shell()
    script = get_init_script(shell)
    print(script)


def _init_global(args):
    import os
    from anzuelo.hook import get_init_script, detect_shell
    shell = args.shell if args.shell != "auto" else detect_shell()
    script = get_init_script(shell)

    rc = os.environ.get("ANZUELO_RC") or {
        "zsh": os.environ.get("ZDOTDIR", os.path.expanduser("~/.zshrc")),
        "bash": os.path.expanduser("~/.bashrc"),
    }.get(shell, os.path.expanduser("~/.profile"))

    try:
        with open(rc) as f:
            content = f.read()
        if "anzuelo init" in content:
            print(f"anzuelo hooks already present in {rc}")
            return
    except (FileNotFoundError, IOError):
        content = ""

    with open(rc, "a") as f:
        f.write("\n# anzuelo: AI coding assistant metrics\n")
        f.write('eval "$(anzuelo init)"\n')

    print(f"anzuelo hooks installed to {rc}")
    print(f"Run: source {rc}")


def cmd_log(args):
    from anzuelo.tracker import log_command, log_api_call, log_tool_call
    sid = args.session_id
    if args.type == "cmd":
        full_cmd = args.detail or args.name
        log_command(full_cmd, args.exit_code, args.duration_ms,
                    output_size=args.output_size, session_id=sid)
    elif args.type == "api":
        log_api_call(
            args.detail or args.name,
            tokens_input=args.tokens_input,
            tokens_output=args.tokens_output,
            endpoint=args.name, session_id=sid,
        )
    elif args.type == "tool":
        log_tool_call(
            args.name,
            detail=args.detail or "",
            exit_code=args.exit_code,
            output_size=args.output_size, session_id=sid,
        )


def cmd_run(args):
    cmd_args = [a for a in args.args if a != "--"]
    if not cmd_args:
        print("error: no command specified", file=sys.stderr)
        sys.exit(1)

    cmd = cmd_args[0]
    rest = cmd_args[1:]

    os.environ["ANZUELO_ACTIVE"] = "1"
    start = time.time()

    if cmd in ("python", "python3") and rest:
        sys.argv = ["anzuelo run", *rest]
        from anzuelo.monitor import install_hooks
        install_hooks()
        import runpy
        target = rest[0]
        sys.argv = rest
        try:
            runpy.run_path(target, run_name="__main__")
            exit_code = 0
        except SystemExit as e:
            exit_code = e.code or 0
        except BaseException:
            import traceback
            traceback.print_exc()
            exit_code = 1
    else:
        exit_code = subprocess.call([cmd, *rest])

    elapsed = int((time.time() - start) * 1000)
    _log_run(cmd_args, exit_code, elapsed)
    sys.exit(exit_code)


def cmd_report(args):
    from anzuelo.tracker import get_summary, get_events, get_live
    sid = getattr(args, 'session', None)

    if args.live:
        _report_live(session_id=sid)
        return

    summary = get_summary(session_id=sid)

    if args.json:
        import json
        if sid:
            summary["session_id"] = sid
        print(json.dumps(summary, indent=2))
        return

    from anzuelo.report import print_report
    events = get_events(limit=args.limit, session_id=sid)
    print_report(summary, events, session_id=sid)


def _report_live(session_id=None):
    from anzuelo.tracker import get_live, get_summary
    from anzuelo.report import print_live
    last_id = 0
    try:
        while True:
            events = get_live(after_id=last_id, session_id=session_id)
            if events:
                last_id = events[-1]["id"]
                summary = get_summary(session_id=session_id)
                print_live(events, summary)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(flush=True)


def cmd_status(args):
    active = os.environ.get("ANZUELO_ACTIVE")
    if active:
        print("anzuelo is ACTIVE")
        print(f"  ANZUELO_ACTIVE={active}")
        from anzuelo.store import _default_path
        db_path = _default_path()
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            print(f"  database: {db_path} ({size} bytes)")
    else:
        print("anzuelo is NOT active")
        print("  Run: eval \"$(anzuelo init)\"")
        print("  Or run: anzuelo run -- <command>")


def cmd_sessions(args):
    from anzuelo.tracker import get_sessions
    from anzuelo.report import print_sessions
    sessions = get_sessions()
    print_sessions(sessions)


def cmd_reset(args):
    from anzuelo.tracker import reset
    sid = getattr(args, 'session', None)
    if sid:
        reset(session_id=sid)
        print(f"Session {sid[:8]} cleared.")
    else:
        reset()
        print("All metrics cleared.")


def main():
    parser = argparse.ArgumentParser(
        prog="anzuelo",
        description="Harness-agnostic metrics and monitoring for AI coding assistants",
    )
    parser.add_argument("--version", action="store_true",
                        help="Show version and exit")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Generate shell hook script for eval")
    p_init.add_argument("--shell", choices=["bash", "zsh", "auto"], default="auto",
                        help="Target shell (default: auto-detect)")
    p_init.add_argument("-g", "--global", dest="global_install", action="store_true",
                        help="Install hooks globally into shell rc file")
    p_init.add_argument("--claude", action="store_true",
                        help="Install hooks for Claude Code")
    p_init.add_argument("--opencode", action="store_true",
                        help="Install hooks for OpenCode")
    p_init.add_argument("--codex", action="store_true",
                        help="Install hooks for Codex CLI")
    p_init.add_argument("--agy", action="store_true",
                        help="Install hooks for Antigravity CLI (agy)")
    p_init.add_argument("--all", dest="all_harnesses", action="store_true",
                        help="Install hooks for all detected AI coding harnesses")

    p_log = sub.add_parser("log", help="Log an event (used by shell hooks)")
    p_log.add_argument("type", choices=["cmd", "api", "tool"])
    p_log.add_argument("name", help="Event name or command")
    p_log.add_argument("detail", nargs="?", default=None,
                       help="Detail string (e.g., full command, model name)")
    p_log.add_argument("exit_code", nargs="?", type=int, default=None)
    p_log.add_argument("duration_ms", nargs="?", type=int, default=None)
    p_log.add_argument("--tokens-input", type=int, default=None)
    p_log.add_argument("--tokens-output", type=int, default=None)
    p_log.add_argument("--output-size", type=int, default=None,
                       help="Size of tool output in characters")
    p_log.add_argument("--session-id", type=str, default=None,
                       help="Session ID (provided by Claude Code hooks)")

    p_run = sub.add_parser("run", help="Run a command with monitoring enabled")
    p_run.add_argument("args", nargs=argparse.REMAINDER)

    p_report = sub.add_parser("report", help="Show metrics report")
    p_report.add_argument("--json", action="store_true",
                          help="Output as JSON")
    p_report.add_argument("--live", action="store_true",
                          help="Live monitoring mode")
    p_report.add_argument("--limit", type=int, default=50,
                          help="Max events to show (default: 50)")
    p_report.add_argument("--session", type=str, default=None,
                          help="Filter by session ID")

    p_sessions = sub.add_parser("sessions", help="List tracked sessions")

    sub.add_parser("status", help="Check if anzuelo hooks are active")

    p_reset = sub.add_parser("reset", help="Clear all collected metrics")
    p_reset.add_argument("--session", type=str, default=None,
                         help="Clear only a specific session")

    args = parser.parse_args()

    if args.version:
        from anzuelo import __version__
        print(f"anzuelo {__version__}")
        return

    if args.command == "init":
        cmd_init(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)
    else:
        parser.print_help()
