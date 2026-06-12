<div align="center">

# 🎣 anzuelo

**See exactly what your AI coding assistant is doing to your codebase.**

[![Pip](https://img.shields.io/badge/pip-install-royalblue?logo=pypi)](https://pypi.org/project/anzuelo/)
[![Homebrew](https://img.shields.io/badge/brew-install-forestgreen?logo=homebrew)](https://github.com/bberastegui/anzuelo)
[![License](https://img.shields.io/badge/license-MIT-silver)](LICENSE)
[![Python](https://img.shields.io/badge/python-≥3.7-gold?logo=python)](pyproject.toml)

**Works with Claude Code · OpenCode · Codex CLI · Antigravity CLI**

---

> *Harness-agnostic, zero-config, stdlib-only metrics & monitoring for AI coding assistants.*

</div>

---

## 🚀 One-liner

```sh
curl -fsSL https://raw.githubusercontent.com/bberastegui/anzuelo/main/install.sh | sh
```

That's it. Install, hook into every AI coding harness you use, and start collecting metrics.

## 📊 The Report

```
╭──────────────────────────────────────────────────────────────────────────────╮
│                              anzuelo  metrics                                 │
╰──────────────────────────────────────────────────────────────────────────────╯

Summary
────────────────────────────────────────────────────────────────────────
composition  ████████████████████░
● 181 commands    ● 0 api calls    ● 10 tool calls

total tokens     0                                                    total events  399
total output     150.1KB                                              tokens/event  0


Top Tools
────────────────────────────────────────────────────────────────────────
Agent    ░░░░░░░░░░░░░░░░░░░░░░░░░      0B    0%  (4 calls)
WebFetch ░░░░░░░░░░░░░░░░░░░░░░░░░      0B    0%  (4 calls)

Top Commands
────────────────────────────────────────────────────────────────────────
#              ████████████████████  94x  100%
🪝 curl         ████░░░░░░░░░░░░░░░░  23x   24%
printf         ███░░░░░░░░░░░░░░░░░  17x   18%
🪝 read         ██░░░░░░░░░░░░░░░░░░   9x   10%
🪝 grep         ██░░░░░░░░░░░░░░░░░░   7x    7%
🪝 ls           █░░░░░░░░░░░░░░░░░░░   4x    4%

Timeline
────────────────────────────────────────────────────────────────────────
14:47:35 > {"url":"https://github.com/..."}
14:47:36 $ grep -i "CVE-2026" /var/log/syslog        286B  (241ms)
14:47:45 > {"url":"https://labs.watchtowr.com/"}
16:41:13 $ echo test-user-flow                          14B   (91ms)
──────────────────────────────────────────────────────────────────────────
                                                       anzuelo report --help
```

## ✨ Features

- **🔌 Harness-agnostic** — Works with Claude Code, OpenCode, Codex CLI, and Antigravity CLI out of the box
- **🚀 Zero config** — Install once, it auto-detects every AI coding harness on your machine
- **📈 Beautiful terminal UI** — Color-coded composition bars, tool breakdowns, and live timeline
- **⏱️ Per-tool timing** — See exactly how long each tool call takes (Read, Write, Bash, Edit, etc.)
- **📏 Output tracking** — Measure how much data each tool produces
- **🔑 Token monitoring** — Track LLM token usage by monkey-patching `requests` and `httpx`
- **📂 Per-session tracking** — Every Claude/Codex session is isolated and queryable
- **👁️ Live mode** — `anzuelo report --live` for real-time monitoring
- **🧹 Clean uninstall** — `anzuelo uninstall --all --global --data` removes everything
- **📦 Zero external dependencies** — Pure Python stdlib, no pip install surprises

## 🎯 Supported Harnesses

| Harness | Auto-detect | Mechanism |
|---------|-------------|-----------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) | `~/.claude/` | PreToolUse/PostToolUse JSON hooks |
| [OpenCode](https://opencode.ai) | `~/.config/opencode/` | Node.js plugin (`tool.execute.before/after`) |
| [Codex CLI](https://github.com/openai/codex) | `~/.codex/` | Plugin manifest + async hooks |
| [Antigravity CLI](https://github.com/antigravity-ai/agy) | `~/.gemini/` | PreToolUse/PostToolUse + BeforeTool/AfterTool |

## 📦 Install

### One-liner (recommended)
```sh
curl -fsSL https://raw.githubusercontent.com/bberastegui/anzuelo/main/install.sh | sh
```
Auto-detects OS, architecture, and all installed AI coding harnesses.

### pip
```sh
pip install anzuelo
anzuelo init --all
```

### Homebrew
```sh
brew install anzuelo
anzuelo init --all
```

### Source
```sh
git clone https://github.com/bberastegui/anzuelo.git
pip install -e anzuelo
anzuelo init --all
```

## 🎮 Usage

### Start tracking
```sh
# Track your terminal commands globally
eval "$(anzuelo init)"

# Track a specific AI coding session
claude   # or opencode, codex, agy — metrics are collected automatically
```

### View the report
```sh
anzuelo report
```

### Live monitoring
```sh
anzuelo report --live
```

### Track a single command
```sh
anzuelo run -- python train.py
anzuelo report
```

### Session management
```sh
anzuelo sessions                    # List all sessions
anzuelo report --session <id>       # Metrics for one session
anzuelo reset --session <id>        # Clear one session
```

### API token tracking
```sh
anzuelo run -- python3 your_script.py
```
Automatically intercepts OpenAI/Anthropic API responses to extract token usage from `requests` and `httpx` calls.

### JSON output
```sh
anzuelo report --json | jq .
```

## 🧹 Uninstall

```sh
anzuelo uninstall --all       # Remove all harness hooks
anzuelo uninstall --global    # Remove shell rc hooks
anzuelo uninstall --data      # Remove metrics database
pip uninstall anzuelo
```

## 🏗️ How It Works

```
Harness hook event (JSON) → anzuelo-hook.sh → anzuelo log → SQLite → report
```

1. **Hooks** — Every supported AI coding harness fires `PreToolUse`/`PostToolUse` events. anzuelo registers lightweight hook scripts that intercept these events.
2. **Logging** — Each event is serialized to a local SQLite database (`~/.local/share/anzuelo/metrics.db`) using WAL mode for concurrent access.
3. **Reporting** — `anzuelo report` queries the database and renders a beautiful terminal UI with composition bars, tool rankings, and a chronological timeline.

## ⚡ CLI Reference

| Command | Description |
|---------|-------------|
| `init` | Generate shell hook script or install harness hooks |
| `log` | Log an event (used internally by hooks) |
| `run` | Run a command with monitoring and API token tracking |
| `report` | Show metrics report (supports `--json`, `--live`, `--session`) |
| `sessions` | List tracked sessions |
| `status` | Check if anzuelo is active |
| `reset` | Clear all metrics or a specific session |
| `uninstall` | Remove hooks (per-harness, global, or data) |

## 📜 License

MIT
