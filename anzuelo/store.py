import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


_local = threading.local()


def _get_connection(path):
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(path or _default_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA busy_timeout=5000")
        _init_schema(conn)
        _local.conn = conn
    return conn


def _default_path():
    data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    db_dir = os.path.join(data_home, "anzuelo")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "metrics.db")


def _init_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            start_time  TEXT NOT NULL,
            end_time    TEXT,
            harness     TEXT DEFAULT 'claude-code',
            metadata    TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT,
            type          TEXT NOT NULL,
            name          TEXT NOT NULL,
            detail        TEXT,
            exit_code     INTEGER,
            duration_ms   INTEGER,
            tokens_input  INTEGER,
            tokens_output INTEGER,
            output_size   INTEGER,
            model         TEXT,
            tool          TEXT,
            timestamp     TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
        CREATE INDEX IF NOT EXISTS idx_events_name ON events(name);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
    """)

    _migrate(conn)


def _migrate(conn):
    existing = [r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "output_size" not in existing:
        conn.execute("ALTER TABLE events ADD COLUMN output_size INTEGER")
    _migrate_companion_commands(conn)


def _migrate_companion_commands(conn):
    """Rename existing companion tool entries (e.g. 'rtk grep foo' -> 'rtk grep')."""
    from anzuelo.hook import detect_companion_tools
    tools = detect_companion_tools()
    for tool in tools:
        rows = conn.execute(
            "SELECT id, name, detail FROM events WHERE type='cmd' AND name=?",
            (tool,)
        ).fetchall()
        for r in rows:
            if r["detail"] and r["detail"].startswith(tool + " "):
                parts = r["detail"].split()
                if len(parts) > 1:
                    new_name = f"{parts[0]} {parts[1]}"
                    if new_name != r["name"]:
                        conn.execute(
                            "UPDATE events SET name=? WHERE id=?",
                            (new_name, r["id"])
                        )
    _migrate_hash_comments(conn)


def _migrate_hash_comments(conn):
    """Rename entries where first word is '#' to the actual command word."""
    rows = conn.execute(
        "SELECT id, name, detail FROM events WHERE type='cmd' AND name='#'"
    ).fetchall()
    for r in rows:
        if r["detail"]:
            parts = r["detail"].split()
            new_name = None
            for p in parts:
                if not p.startswith("#"):
                    new_name = p
                    break
            if new_name is None:
                new_name = parts[0]
            if new_name != r["name"]:
                conn.execute(
                    "UPDATE events SET name=? WHERE id=?",
                    (new_name, r["id"])
                )


def _now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or _default_path()

    def _conn(self):
        return _get_connection(self.path)

    def ensure_session(self, session_id, harness="claude-code"):
        conn = self._conn()
        with conn:
            cur = conn.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,))
            if cur.fetchone() is None:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (id, start_time, harness) VALUES (?, ?, ?)",
                    (session_id, _now(), harness),
                )

    def log_event(self, type, name, detail=None, exit_code=None,
                  duration_ms=None, tokens_input=None, tokens_output=None,
                  output_size=None, model=None, tool=None,
                  session_id=None, timestamp=None):
        conn = self._conn()
        if session_id:
            self.ensure_session(session_id)
        with conn:
            conn.execute("""
                INSERT INTO events
                    (session_id, type, name, detail, exit_code, duration_ms,
                     tokens_input, tokens_output, output_size, model, tool, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, type, name, detail, exit_code, duration_ms,
                tokens_input, tokens_output, output_size, model, tool,
                timestamp or _now()
            ))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_events(self, limit=100, offset=0, type=None, session_id=None):
        conn = self._conn()
        parts = ["SELECT * FROM events"]
        params = []
        conds = []
        if type:
            conds.append("type=?")
            params.append(type)
        if session_id:
            conds.append("session_id=?")
            params.append(session_id)
        if conds:
            parts.append("WHERE " + " AND ".join(conds))
        parts.append("ORDER BY id DESC LIMIT ? OFFSET ?")
        params.extend([limit, offset])
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self, session_id=None):
        conn = self._conn()
        params = []
        cond = ""
        if session_id:
            cond = " WHERE session_id=?"
            params.append(session_id)

        total_events = conn.execute(
            f"SELECT COUNT(*) FROM events{cond}", params
        ).fetchone()[0]

        cmd_count = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE type='cmd' AND output_size IS NOT NULL{cond and ' AND session_id=?' or ''}",
            params if session_id else []
        ).fetchone()[0]

        api_count = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE type='api'{cond}",
            params if session_id else []
        ).fetchone()[0]

        tool_count = conn.execute(
            f"SELECT COUNT(*) FROM events WHERE type='tool' AND output_size IS NOT NULL{cond and ' AND session_id=?' or ''}",
            params if session_id else []
        ).fetchone()[0]

        total_tokens = conn.execute(
            f"SELECT COALESCE(SUM(tokens_input),0) + COALESCE(SUM(tokens_output),0) FROM events{cond}",
            params if session_id else []
        ).fetchone()[0]

        total_output = conn.execute(
            f"SELECT COALESCE(SUM(output_size),0) FROM events{cond}",
            params if session_id else []
        ).fetchone()[0]

        where_cmd = f"WHERE type='cmd' AND output_size IS NOT NULL{cond and ' AND session_id=?' or ''}"
        top_cmds = [
            dict(r) for r in conn.execute(
                f"SELECT name, COUNT(*) as count FROM events {where_cmd} GROUP BY name ORDER BY count DESC LIMIT 10",
                params if session_id else []
            ).fetchall()
        ]

        models = [
            dict(r) for r in conn.execute(
                f"SELECT model, COUNT(*) as count, "
                "COALESCE(SUM(tokens_input),0) as tokens_in, "
                "COALESCE(SUM(tokens_output),0) as tokens_out "
                f"FROM events WHERE type='api' AND model IS NOT NULL{cond and ' AND session_id=?' or ''} "
                "GROUP BY model ORDER BY count DESC",
                params if session_id else []
            ).fetchall()
        ]

        where_tool = f"WHERE type='tool' AND output_size IS NOT NULL{cond and ' AND session_id=?' or ''}"
        top_tools = [
            dict(r) for r in conn.execute(
                f"SELECT name, COUNT(*) as count, "
                "COALESCE(SUM(output_size),0) as total_output "
                f"FROM events {where_tool} GROUP BY name ORDER BY count DESC LIMIT 10",
                params if session_id else []
            ).fetchall()
        ]

        return {
            "total_events": total_events,
            "commands": cmd_count,
            "api_calls": api_count,
            "tool_calls": tool_count,
            "total_tokens": total_tokens,
            "total_output_chars": total_output,
            "top_commands": top_cmds,
            "top_tools": top_tools,
            "models": models,
        }

    def get_sessions(self):
        conn = self._conn()
        rows = conn.execute("""
            SELECT s.id, s.start_time, s.end_time, s.harness,
                   COUNT(e.id) as event_count
            FROM sessions s
            LEFT JOIN events e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY s.start_time DESC
            LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]

    def get_live(self, after_id=0, session_id=None):
        conn = self._conn()
        parts = ["SELECT * FROM events WHERE id>?"]
        params = [after_id]
        if session_id:
            parts.append("AND session_id=?")
            params.append(session_id)
        parts.append("ORDER BY id ASC")
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    def clear(self, session_id=None):
        conn = self._conn()
        with conn:
            if session_id:
                conn.execute("DELETE FROM events WHERE session_id=?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            else:
                conn.execute("DELETE FROM events")
                conn.execute("DELETE FROM sessions")

    def close(self):
        conn = getattr(_local, "conn", None)
        if conn:
            conn.close()
            _local.conn = None
