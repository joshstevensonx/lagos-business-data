"""Resumable run state in SQLite (SPEC §2.2).

A search is attempted only if it is not `done`. Re-running the same command is a
no-op for completed work; --force-term / --force-area reset specific cells.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    source      TEXT NOT NULL,
    term        TEXT NOT NULL,
    area        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | error | skipped
    raw_count   INTEGER,
    kept_count  INTEGER,
    started_at  TEXT,
    finished_at TEXT,
    error       TEXT,
    PRIMARY KEY (source, term, area)
);
CREATE TABLE IF NOT EXISTS stages (
    name        TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    finished_at TEXT,
    detail      TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class State:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        # a search left 'running' means the process died mid-search: it never completed
        self.db.execute("UPDATE searches SET status='pending' WHERE status='running'")
        self.db.commit()

    def close(self):
        self.db.close()

    # ------------------------------------------------------------ searches
    def is_done(self, source: str, term: str, area: str) -> bool:
        row = self.db.execute('SELECT status FROM searches WHERE source=? AND term=? AND area=?',
                              (source, term, area)).fetchone()
        return bool(row) and row['status'] == 'done'

    def start(self, source: str, term: str, area: str):
        self.db.execute(
            """INSERT INTO searches(source, term, area, status, started_at) VALUES (?,?,?,'running',?)
               ON CONFLICT(source, term, area) DO UPDATE SET status='running', started_at=excluded.started_at,
               error=NULL, finished_at=NULL""", (source, term, area, now()))
        self.db.commit()

    def finish(self, source: str, term: str, area: str, raw_count: int):
        self.db.execute("""UPDATE searches SET status='done', raw_count=?, finished_at=?
                           WHERE source=? AND term=? AND area=?""", (raw_count, now(), source, term, area))
        self.db.commit()

    def fail(self, source: str, term: str, area: str, error: str, status: str = 'error'):
        self.db.execute(
            """INSERT INTO searches(source, term, area, status, finished_at, error) VALUES (?,?,?,?,?,?)
               ON CONFLICT(source, term, area) DO UPDATE SET status=excluded.status,
               finished_at=excluded.finished_at, error=excluded.error""",
            (source, term, area, status, now(), error[:500]))
        self.db.commit()

    def set_kept(self, counts: dict[tuple[str, str, str], int]):
        self.db.execute('UPDATE searches SET kept_count=0 WHERE status=\'done\'')
        for (source, term, area), n in counts.items():
            self.db.execute('UPDATE searches SET kept_count=? WHERE source=? AND term=? AND area=?',
                            (n, source, term, area))
        self.db.commit()

    def force(self, terms: list[str] | None = None, areas: list[str] | None = None) -> int:
        n = 0
        for t in terms or []:
            n += self.db.execute("UPDATE searches SET status='pending' WHERE term=?", (t,)).rowcount
        for a in areas or []:
            n += self.db.execute("UPDATE searches SET status='pending' WHERE area=?", (a,)).rowcount
        self.db.commit()
        return n

    def searches(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM searches ORDER BY started_at, source, term, area')]

    # -------------------------------------------------------------- stages
    def stage_done(self, name: str, detail: str = ''):
        self.db.execute("""INSERT INTO stages(name, status, finished_at, detail) VALUES (?, 'done', ?, ?)
                           ON CONFLICT(name) DO UPDATE SET status='done', finished_at=excluded.finished_at,
                           detail=excluded.detail""", (name, now(), detail))
        self.db.commit()

    def stages(self) -> dict[str, dict]:
        return {r['name']: dict(r) for r in self.db.execute('SELECT * FROM stages')}
