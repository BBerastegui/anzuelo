# anzuelo — Agent Instructions

## Auto-Report on Session End

When an AI coding assistant session ends (user exits `claude`, `opencode`, `codex`, or `agy`), the shell hooks (`_BASH_HOOK`/`_ZSH_HOOK`) detect the exit and run `anzuelo finish`.

The mechanism: on every `__anzuelo_precmd` invocation (which already fires after every shell command), the hook extracts the first word of the just-completed command. If it matches a known AI tool, it calls `anzuelo finish`. This is 3 extra lines in an existing hook — no new shell-wide filtering, no background processes, no timers.

`anzuelo finish` ends the last active session (sets `end_time`) and prints the report. It accepts `--session <id>` to finish a specific session.

## Project
Harness-agnostic lightweight metrics & monitoring for AI coding assistants.
Install: `brew install anzuelo` or `pip install anzuelo`

## Architecture

### Data Flow
```
Harness hook event (JSON on stdin) → anzuelo-hook.sh → anzuelo log → SQLite → report
```

### File Map
| File | Purpose |
|------|---------|
| `anzuelo/cli.py` | CLI dispatch: `init`, `log`, `run`, `report`, `sessions`, `status`, `reset` |
| `anzuelo/hook.py` | Shell hook scripts, Claude/Codex/Antigravity hook script template, OpenCode plugin template, harness installers |
| `anzuelo/store.py` | SQLite layer: `events` + `sessions` tables, WAL mode, busy_timeout=5000 |
| `anzuelo/tracker.py` | High-level event recording wrappers around store |
| `anzuelo/report.py` | Terminal UI: bordered headers, bar charts, timeline |
| `anzuelo/monitor.py` | Monkey-patches `requests.Session.send` + `httpx.Client.send` for token extraction |
| `install.sh` | One-liner installer (curl pipe), calls `anzuelo init --all` |
| `Formula/anzuelo.rb` | Homebrew formula |
| `AGENTS.md` | This file |

## Harness Support

Each harness gets hooks installed by `anzuelo init --<name>`:

| Key | Harness | Mechanism | Hook Names | Detection |
|-----|---------|-----------|------------|-----------|
| `claude` | Claude Code | stdin/stdout JSON command hooks | `PreToolUse`/`PostToolUse` | `~/.claude/` exists |
| `opencode` | OpenCode | Node.js plugin (`export const server`) | `tool.execute.before`/`after` | `~/.config/opencode/` exists |
| `codex` | Codex CLI | Plugin manifest + stdin/stdout JSON | `preToolUse`/`postToolUse` | `~/.codex/` exists |
| `agy` | Antigravity CLI | stdin/stdout JSON, also Gemini legacy | `PreToolUse`/`PostToolUse` + `BeforeTool`/`AfterTool` | `~/.gemini/` exists |

### Companion Tool Detection

anzuelo detects "companion tools" (like RTK) that hook into the same harness and rewrites command names so you see what the companion actually *did*, not just that it was called.

Detection is **fully agnostic** — anzuelo scans `~/.claude/hooks/` and harness config files for any executable hook scripts that aren't its own, and derives the companion name from the filename (e.g., `rtk-rewrite.sh` → `rtk`).

`tracker.py::_companion_name()` uses the first two words (`"rtk grep"`) instead of just the first word (`"rtk"`) for command grouping.

New entries get the two-word name automatically. Existing entries are migrated by `_migrate_companion_commands()` in `store.py`.

The report header shows companion tools in orange: `anzuelo metrics (RTK enabled)`. `anzuelo status` also shows them.

In `report.py`, companion-routed commands get the 🪝 emoji + orange color instead of green, and only the clean subcommand name is shown (e.g., `🪝 curl` instead of `rtk curl`). The bar is also orange. This makes it immediately obvious which commands were intercepted by a companion.

### Adding a New Harness

Touch exactly **4 places**:

1. **`anzuelo/hook.py`** — Add config path constants + `install_<name>_hooks()` function
2. **`anzuelo/hook.py`** — Add entry to `_HARNESSES` dict (label + detection lambda)
3. **`anzuelo/hook.py`** — Add entry to `_HARNESS_INSTALLERS` dict
4. **`anzuelo/cli.py`** — Add `--<name>` flag to `p_init.add_argument(...)` in `main()`

5. **`AGENTS.md`** — Add the new harness to the support table and verify the "Adding a New Harness" instructions still apply.

Detection pattern: check for the harness's config directory. `install.sh` already calls `anzuelo init --all` which auto-detects via `_HARNESSES`.

If the hook uses stdin/stdout JSON protocol (most do), reuse `_HOOK_SCRIPT` via `_write_hook_script()` and `_add_hooks_to_json()`. If it uses a different mechanism (like OpenCode's Node.js plugin), create a separate template.

**When changing conventions (arg order, protocol, schema):** update the "Critical Conventions" and "The Hook Script Protocol" sections in this file so all agents stay consistent.

### Uninstalling a Harness

Each `install_<name>_hooks()` has a matching `uninstall_<name>_hooks()` in `hook.py`. They reverse the install:

1. **`_remove_hooks_from_json()`** — strips our hook entries from the config file, removes the file if emptied
2. **`uninstall_<name>_hooks()`** — removes hook script + plugin files + config entries

Add the uninstaller to `_HARNESS_UNINSTALLERS` dict and wire up via `cli.py` (the `--<name>` flag on `anzuelo uninstall`).

`anzuelo uninstall` also supports `--global` (shell rc cleanup) and `--data` (database removal).

## The Hook Script Protocol

The universal `_HOOK_SCRIPT` (`anzuelo-hook.sh`) handles `PreToolUse` and `PostToolUse` events:

- Reads JSON from **stdin**
- Extracts: `tool_name`, `tool_input`, `hook_event_name`, `session_id`, `tool_response`, `duration_ms`
- **PreToolUse**: logs `type=cmd` (Bash) or `type=tool` (all others) with name, detail, session_id
- **PostToolUse**: logs same + exit_code=0, duration_ms, output_size (from `tool_response.stdout` or `tool_response.file.content`)
- Calls `anzuelo log ...` with positional args **before** optional args (argparse `nargs="?"` bug workaround)

## Token Tracking Convention

Token consumption is tracked **opt-in via environment variables** — no HTTP interception:

- **`ANZUELO_TOKENS_INPUT`** — set by companion tools (RTK, etc.) before PostToolUse fires
- **`ANZUELO_TOKENS_OUTPUT`** — same, set by tools to report their own token usage
- The hook script reads these with `os.environ.pop()` (consumed once) and passes them as `--tokens-input`/`--tokens-output` to `anzuelo log`
- Companions know their own token consumption internally from API responses; they export the env vars so anzuelo can log them
- The report shows per-command token totals in the `Top Commands` section

This replaces the old `monitor.py` HTTP monkey-patching approach.

## Critical Conventions

- **PostToolUse dedup**: Summary queries filter `WHERE type='cmd' AND output_size IS NOT NULL` to count only PostToolUse events (PreToolUse has NULL output_size)
- **Comment skipping**: `_first_word()` in `tracker.py` skips leading `#` comments when extracting the command name from a multi-line bash command
- **Event types**: `type='cmd'` for Bash (name from first word), `type='tool'` for all others (name is tool name like Read/Write/Glob)
- **Arg order for `anzuelo log`**: positional args (`exit_code`, `duration_ms`) must come BEFORE optional args (`--session-id`, `--output-size`). Argparse with `nargs="?"` stops consuming positionals after seeing an optional.
- **Bash in PostToolUse**: uses `tool_response.stdout`, NOT `tool_result` (that key is never present)
- **Read in PostToolUse**: uses `tool_response.file.content`
- **Session auto-creation**: `log_event()` calls `ensure_session()` when session_id provided; session row created on first event per session_id
- **Python 3.7+ with Rich**: terminal UI uses [Rich](https://github.com/Textualize/rich) for cross-platform rendering; no other external dependencies

## Testing

- Manual: run `claude --dangerously-skip-permissions -p 'run: echo test' && anzuelo report`
- Verify both PreToolUse and PostToolUse events appear in report (two timeline entries per tool call)
- Check SQLite directly: `sqlite3 ~/.local/share/anzuelo/metrics.db "SELECT * FROM events ORDER BY id DESC LIMIT 5;"`
- After any hook script change: re-run `anzuelo init --<harness>` to install it
