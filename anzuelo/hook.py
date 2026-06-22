import os
import shlex


_BASH_HOOK = r'''
__anzuelo_start_time=""
__anzuelo_last_cmd=""

__anzuelo_preexec() {
    __anzuelo_last_cmd="$BASH_COMMAND"
    __anzuelo_start_time=$(date +%s%N 2>/dev/null || echo 0)
}

__anzuelo_precmd() {
    local exit_code=$?
    local last_cmd="$__anzuelo_last_cmd"
    if [[ -n "$last_cmd" && "$last_cmd" != \ * && "$last_cmd" != anzuelo* ]]; then
        local duration=0
        if [[ -n "$__anzuelo_start_time" && "$__anzuelo_start_time" != "0" ]]; then
            local end_time=$(date +%s%N 2>/dev/null)
            if [[ -n "$end_time" && "$end_time" -gt "$__anzuelo_start_time" 2>/dev/null ]]; then
                duration=$(( (end_time - __anzuelo_start_time) / 1000000 ))
            fi
        fi
        anzuelo log cmd "$last_cmd" "$exit_code" "$duration" 2>/dev/null || true
        local tool="${last_cmd%% *}"
        case "$tool" in
            claude|opencode|codex|agy) anzuelo finish 2>/dev/null || true ;;
        esac
    fi
    __anzuelo_last_cmd=""
    __anzuelo_start_time=""
}

trap '__anzuelo_preexec' DEBUG
PROMPT_COMMAND="__anzuelo_precmd${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
export ANZUELO_ACTIVE=1
'''


_ZSH_HOOK = r'''
__anzuelo_start_time=""
__anzuelo_last_cmd=""

__anzuelo_preexec() {
    __anzuelo_last_cmd="$1"
    __anzuelo_start_time=$EPOCHREALTIME
}

__anzuelo_precmd() {
    local exit_code=$?
    local last_cmd="$__anzuelo_last_cmd"
    if [[ -n "$last_cmd" && "$last_cmd" != anzuelo* ]]; then
        local end_time=$EPOCHREALTIME
        local duration=$(( (${end_time/.} - ${__anzuelo_start_time/.}) / 1000 ))
        anzuelo log cmd "$last_cmd" "$exit_code" "$duration" 2>/dev/null || true
        local tool="${last_cmd%% *}"
        case "$tool" in
            claude|opencode|codex|agy) anzuelo finish 2>/dev/null || true ;;
        esac
    fi
    __anzuelo_last_cmd=""
    __anzuelo_start_time=""
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec __anzuelo_preexec
add-zsh-hook precmd __anzuelo_precmd
export ANZUELO_ACTIVE=1
'''


def detect_shell():
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "bash" in shell:
        return "bash"
    return "sh"


def get_init_script(shell=None):
    if shell is None or shell == "auto":
        shell = detect_shell()
    if shell == "zsh":
        return _ZSH_HOOK.strip()
    return _BASH_HOOK.strip()


# ── Universal hook script ────────────────────────────────────────────
# Works with any harness that passes PreToolUse/PostToolUse JSON on stdin
# Supported: Claude Code, Codex CLI, Antigravity CLI (agy)
_HOOK_SCRIPT = '''#!/usr/bin/env bash
set -euo pipefail
INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json, os, subprocess, sys

try:
    d = json.loads(sys.argv[1])
    tool_name = d.get("tool_name", "")
    tool_input = d.get("tool_input", {})
    event_name = d.get("hook_event_name", "")
    session_id = d.get("session_id", "")

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        detail = cmd[:500]
        etype = "cmd"
    else:
        fp = tool_input.get("file_path") or tool_input.get("pattern") or ""
        detail = str(fp)[:500] or json.dumps(tool_input, separators=(",", ":"))[:500]
        etype = "tool"

    output = ""
    exit_code = None
    duration = 0
    if event_name == "PostToolUse":
        tresp = d.get("tool_response")
        if isinstance(tresp, dict):
            fc = tresp.get("file")
            if isinstance(fc, dict) and "content" in fc:
                output = fc.get("content", "")
                exit_code = 0
            elif "stdout" in tresp:
                output = tresp.get("stdout", "")
            duration = d.get("duration_ms", 0)

    if event_name == "PostToolUse" and (output or duration):
        ec = exit_code if exit_code is not None else 0
        cmd = ["anzuelo", "log", etype, tool_name, detail[:500],
               str(ec), str(duration), "--output-size", str(len(output))]
        if session_id:
            cmd.extend(["--session-id", session_id])
        tin = os.environ.pop("ANZUELO_TOKENS_INPUT", "")
        tout = os.environ.pop("ANZUELO_TOKENS_OUTPUT", "")
        if tin:
            cmd.extend(["--tokens-input", tin])
        if tout:
            cmd.extend(["--tokens-output", tout])
        subprocess.run(cmd, capture_output=True, timeout=5)
    elif event_name == "PreToolUse":
        base = ["anzuelo", "log", etype, tool_name, detail[:500]]
        if session_id:
            base.extend(["--session-id", session_id])
        subprocess.run(base, capture_output=True, timeout=5)
except Exception:
    pass
PYEOF
echo "$INPUT"
'''


# ── OpenCode Node.js plugin ──────────────────────────────────────────
_OPENCODE_PLUGIN = '''// anzuelo metrics plugin for OpenCode
// Installed by: anzuelo init --opencode
export const server = async (input) => {
  const hooks = {
    "tool.execute.before": async (hookInput, hookOutput) => {
      const { tool, sessionID } = hookInput;
      const isBash = tool.toLowerCase() === "bash";
      const etype = isBash ? "cmd" : "tool";
      let detail = "";
      if (isBash && hookOutput.args) {
        detail = hookOutput.args.command || "";
      } else if (hookOutput.args) {
        detail = hookOutput.args.file_path || hookOutput.args.pattern || JSON.stringify(hookOutput.args);
      }
      const { spawnSync } = await import("child_process");
      try {
        spawnSync("anzuelo", ["log", etype, tool, detail.slice(0, 500), "--session-id", sessionID], { timeout: 5000, stdio: "ignore" });
      } catch (e) {}
    },
    "tool.execute.after": async (hookInput, hookOutput) => {
      const { tool, sessionID } = hookInput;
      const isBash = tool.toLowerCase() === "bash";
      const etype = isBash ? "cmd" : "tool";
      const outputSize = String((hookOutput.output || "").length);
      const { spawnSync } = await import("child_process");
      try {
        spawnSync("anzuelo", ["log", etype, tool, "", "0", "0", "--output-size", outputSize, "--session-id", sessionID], { timeout: 5000, stdio: "ignore" });
      } catch (e) {}
    }
  };
  return hooks;
};
'''


# ── Harness config paths ────────────────────────────────────────────
CLAUDE_HOOK_DIR = os.path.expanduser("~/.claude/hooks")
CLAUDE_SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")

CODEX_PLUGIN_DIR = os.path.expanduser("~/.codex/plugins")
CODEX_HOOKS_DIR = os.path.expanduser("~/.codex/hooks")

OPENCODE_PLUGIN_DIR = os.path.expanduser("~/.config/opencode/plugins")

AGY_HOOKS_DIR = os.path.expanduser("~/.gemini/hooks")
AGY_HOOKS_CONFIG = os.path.expanduser("~/.gemini/config/hooks.json")
GEMINI_SETTINGS_PATH = os.path.expanduser("~/.gemini/settings.json")


# ── Helpers ──────────────────────────────────────────────────────────

def _write_hook_script(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_HOOK_SCRIPT.strip())
        f.write("\n")
    os.chmod(path, 0o755)


def _add_hooks_to_json(path, events, hook_path, config_key="hooks"):
    import json as _json
    if os.path.exists(path):
        with open(path) as f:
            cfg = _json.load(f)
    else:
        cfg = {}
    cfg.setdefault(config_key, {})

    hook_entry = [
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": hook_path}
            ],
        }
    ]

    for event in events:
        existing = cfg[config_key].get(event, [])
        already = any(
            h["command"] == hook_path
            for g in existing
            for h in g.get("hooks", [])
        )
        if not already:
            existing.extend(hook_entry)
            cfg[config_key][event] = existing

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        _json.dump(cfg, f, indent=2)
        f.write("\n")
    label = os.path.basename(os.path.dirname(path)) or "config"
    print(f"  added anzuelo hooks to {path}")


def _remove_hooks_from_json(path, events, hook_path, config_key="hooks"):
    import json as _json
    if not os.path.exists(path):
        return
    with open(path) as f:
        cfg = _json.load(f)
    if config_key not in cfg:
        return
    changed = False
    for event in events:
        existing = cfg[config_key].get(event, [])
        filtered = [
            g for g in existing
            if not any(h.get("command") == hook_path for h in g.get("hooks", []))
        ]
        if len(filtered) != len(existing):
            changed = True
            if filtered:
                cfg[config_key][event] = filtered
            elif event in cfg[config_key]:
                del cfg[config_key][event]
    if not changed:
        return
    if not cfg[config_key]:
        del cfg[config_key]
    if not cfg:
        os.remove(path)
        print(f"  removed {path}")
    else:
        with open(path, "w") as f:
            _json.dump(cfg, f, indent=2)
            f.write("\n")


# ── Companion tools ──────────────────────────────────────────────────

_ANZUELO_HOOK_SCRIPTS = {"anzuelo-hook.sh"}


def _derive_companion_name(filename):
    """Derive companion tool name from a hook script filename.
    rtk-rewrite.sh -> (rtk, RTK)
    headroom-hook.sh -> (headroom, Headroom)
    my-tool-hook.sh -> (my-tool, My-Tool)
    """
    name = filename.rsplit(".", 1)[0]  # strip .sh / .sha256
    for suffix in ["-rewrite", "-hook"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if len(name) <= 4:
        label = name.upper()
    else:
        label = name[0].upper() + name[1:]
    return name, label


def _is_anzuelo_file(fname):
    """Check if a filename belongs to anzuelo (any variant)."""
    return fname.startswith("anzuelo") or fname in _ANZUELO_HOOK_SCRIPTS


def _scan_claude_hooks():
    """Auto-detect companion tools by scanning ~/.claude/hooks/ for
    any registered hook scripts that aren't anzuelo's."""
    tools = {}
    hook_dir = os.path.expanduser("~/.claude/hooks")
    if not os.path.isdir(hook_dir):
        return tools
    for f in os.listdir(hook_dir):
        if _is_anzuelo_file(f):
            continue
        fpath = os.path.join(hook_dir, f)
        if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
            name, label = _derive_companion_name(f)
            if name:
                tools[name] = {"label": label, "hook_file": fpath}
    return tools


def _scan_settings_json():
    """Scan ~/.claude/settings.json for hooks not registered by anzuelo."""
    tools = {}
    path = os.path.expanduser("~/.claude/settings.json")
    if not os.path.exists(path):
        return tools
    try:
        import json as _json
        with open(path) as f:
            cfg = _json.load(f)
    except Exception:
        return tools
    hooks_cfg = cfg.get("hooks", {})
    for event, groups in hooks_cfg.items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                if cmd and not _is_anzuelo_file(os.path.basename(cmd)) \
                       and "anzuelo" not in cmd:
                    fname = os.path.basename(cmd)
                    name, label = _derive_companion_name(fname)
                    if name and name not in tools:
                        tools[name] = {"label": label, "hook_file": cmd}
    return tools


def _scan_harness_companions():
    """Aggregate companion tools from all scan sources."""
    tools = {}
    for scanner in (_scan_claude_hooks, _scan_settings_json):
        tools.update(scanner())
    return tools


def detect_companion_tools():
    return list(_scan_harness_companions().keys())


def get_companion_info():
    tools = _scan_harness_companions()
    return [(name, info["label"]) for name, info in tools.items()]


# ── Harness installers ───────────────────────────────────────────────

def install_claude_hooks():
    hook_path = os.path.join(CLAUDE_HOOK_DIR, "anzuelo-hook.sh")
    _write_hook_script(hook_path)
    print(f"  created {hook_path}")
    _add_hooks_to_json(CLAUDE_SETTINGS_PATH, ("PreToolUse", "PostToolUse"), hook_path)


def install_opencode_hooks():
    os.makedirs(OPENCODE_PLUGIN_DIR, exist_ok=True)
    plugin_path = os.path.join(OPENCODE_PLUGIN_DIR, "anzuelo.js")
    with open(plugin_path, "w") as f:
        f.write(_OPENCODE_PLUGIN.strip())
        f.write("\n")
    print(f"  created {plugin_path}")
    print(f"  restart opencode to load the anzuelo plugin")


def install_codex_hooks():
    hook_path = os.path.join(CODEX_HOOKS_DIR, "anzuelo-hook.sh")
    _write_hook_script(hook_path)
    print(f"  created {hook_path}")

    plugin_path = os.path.join(CODEX_PLUGIN_DIR, "anzuelo")
    os.makedirs(plugin_path, exist_ok=True)
    manifest = {
        "name": "anzuelo",
        "version": "0.1.0",
        "description": "Lightweight AI coding metrics",
        "hooks": {
            "preToolUse": {
                "handler_type": "command",
                "execution_mode": "async",
                "source_path": hook_path,
                "timeout": 5000,
            },
            "postToolUse": {
                "handler_type": "command",
                "execution_mode": "async",
                "source_path": hook_path,
                "timeout": 5000,
            },
        },
    }
    manifest_path = os.path.join(plugin_path, "plugin.json")
    import json
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"  created {manifest_path}")
    print(f"  NOTE: run 'codex plugin install {plugin_path}' or restart codex")


def install_agy_hooks():
    hook_path = os.path.join(AGY_HOOKS_DIR, "anzuelo-hook.sh")
    _write_hook_script(hook_path)
    print(f"  created {hook_path}")

    _add_hooks_to_json(AGY_HOOKS_CONFIG, ("PreToolUse", "PostToolUse"), hook_path)

    if os.path.exists(GEMINI_SETTINGS_PATH):
        _add_hooks_to_json(GEMINI_SETTINGS_PATH, ("BeforeTool", "AfterTool"), hook_path)


# ── Uninstallers ─────────────────────────────────────────────────────

def uninstall_claude_hooks():
    hook_path = os.path.join(CLAUDE_HOOK_DIR, "anzuelo-hook.sh")
    _remove_hooks_from_json(CLAUDE_SETTINGS_PATH, ("PreToolUse", "PostToolUse"), hook_path)
    if os.path.exists(hook_path):
        os.remove(hook_path)
        print(f"  removed {hook_path}")
    for f in os.listdir(CLAUDE_HOOK_DIR):
        if f.startswith("anzuelo-hook.sh") and f != "anzuelo-hook.sh":
            fpath = os.path.join(CLAUDE_HOOK_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
                print(f"  removed {fpath}")


def uninstall_opencode_hooks():
    plugin_path = os.path.join(OPENCODE_PLUGIN_DIR, "anzuelo.js")
    if os.path.exists(plugin_path):
        os.remove(plugin_path)
        print(f"  removed {plugin_path}")


def uninstall_codex_hooks():
    hook_path = os.path.join(CODEX_HOOKS_DIR, "anzuelo-hook.sh")
    if os.path.exists(hook_path):
        os.remove(hook_path)
        print(f"  removed {hook_path}")
    plugin_dir = os.path.join(CODEX_PLUGIN_DIR, "anzuelo")
    if os.path.exists(plugin_dir):
        import shutil
        shutil.rmtree(plugin_dir)
        print(f"  removed {plugin_dir}")


def uninstall_agy_hooks():
    hook_path = os.path.join(AGY_HOOKS_DIR, "anzuelo-hook.sh")
    _remove_hooks_from_json(AGY_HOOKS_CONFIG, ("PreToolUse", "PostToolUse"), hook_path)
    if os.path.exists(GEMINI_SETTINGS_PATH):
        _remove_hooks_from_json(GEMINI_SETTINGS_PATH, ("BeforeTool", "AfterTool"), hook_path)
    if os.path.exists(hook_path):
        os.remove(hook_path)
        print(f"  removed {hook_path}")
    hooks_dir = AGY_HOOKS_DIR
    if os.path.isdir(hooks_dir) and not os.listdir(hooks_dir):
        os.rmdir(hooks_dir)
        print(f"  removed empty {hooks_dir}")


_HARNESSES = {
    "claude": ("Claude Code", lambda: os.path.exists(os.path.expanduser("~/.claude"))),
    "opencode": ("OpenCode", lambda: os.path.exists(os.path.expanduser("~/.config/opencode"))),
    "codex": ("Codex CLI", lambda: os.path.exists(os.path.expanduser("~/.codex"))),
    "agy": ("Antigravity CLI", lambda: os.path.exists(os.path.expanduser("~/.gemini"))),
}

_HARNESS_INSTALLERS = {
    "claude": install_claude_hooks,
    "opencode": install_opencode_hooks,
    "codex": install_codex_hooks,
    "agy": install_agy_hooks,
}

_HARNESS_UNINSTALLERS = {
    "claude": uninstall_claude_hooks,
    "opencode": uninstall_opencode_hooks,
    "codex": uninstall_codex_hooks,
    "agy": uninstall_agy_hooks,
}


def detect_harnesses():
    found = []
    for name, (label, check) in _HARNESSES.items():
        if check():
            found.append(name)
    return found


def install_hooks(harness_name):
    installer = _HARNESS_INSTALLERS.get(harness_name)
    if installer:
        installer()
    else:
        print(f"  unknown harness: {harness_name}")
        print(f"  available: {', '.join(_HARNESS_INSTALLERS)}")


def uninstall_hooks(harness_name):
    uninstaller = _HARNESS_UNINSTALLERS.get(harness_name)
    if uninstaller:
        uninstaller()
    else:
        print(f"  unknown harness: {harness_name}")
        print(f"  available: {', '.join(_HARNESS_UNINSTALLERS)}")


# ── Run wrapper ──────────────────────────────────────────────────────

def get_run_wrapper(cmd_parts):
    anzuelo_bin = shlex.quote(os.environ.get("_ANZUELO_BIN", "anzuelo"))
    cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)
    return f"""\
export ANZUELO_ACTIVE=1
if command -v python3 >/dev/null 2>&1; then
    ANZUELO_PY="python3"
elif command -v python >/dev/null 2>&1; then
    ANZUELO_PY="python"
else
    ANZUELO_PY=""
fi
if [ -n "$ANZUELO_PY" ] && $ANZUELO_PY -c "import anzuelo.monitor" 2>/dev/null; then
    exec $ANZUELO_PY -m anzuelo.monitor {cmd_str}
else
    exec {cmd_str}
fi
"""
