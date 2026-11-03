import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.models import InvestigationInput, Report


def now() -> str:
    return datetime.now(UTC).isoformat()


class AdmissionError(Exception):
    pass


class PostgresConnection:
    """Small parameter adapter for the shared fixed SQL statements; no dynamic user SQL."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql: str, params=()):
        return self.connection.execute(sql.replace("?", "%s"), params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False


class Store:
    def __init__(self, path: str):
        self.postgres = path.startswith(("postgres://", "postgresql://"))
        if not self.postgres:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._pg_connection: psycopg.Connection[dict] | None = None
        with self.connect() as db:
            if not self.postgres:
                db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, request TEXT NOT NULL,
                progress TEXT NOT NULL, report TEXT, error TEXT)""")

    def connect(self):
        if self.postgres:
            if self._pg_connection is None or self._pg_connection.closed:
                self._pg_connection = psycopg.connect(
                    self.path,
                    connect_timeout=10,
                    row_factory=dict_row,
                    options="-c statement_timeout=5000",
                )
            return PostgresConnection(self._pg_connection)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def close(self):
        if self._pg_connection is not None:
            self._pg_connection.close()

    def recover(self):
        with self.connect() as db:
            db.execute(
                """UPDATE runs SET status='failed', error=?, updated_at=?
                WHERE status IN ('queued','running')""",
                (
                    "Application restarted before completion. Submit a new run; no automatic model replay.",
                    now(),
                ),
            )

    def create(
        self,
        request: InvestigationInput,
        daily: int = 20,
        capacity: int = 200,
        *,
        enforce_submission_limits: bool = True,
    ) -> str:
        stamp = now()
        with self.connect() as db:
            if self.postgres:
                db.execute("SELECT pg_advisory_xact_lock(718204301)")
            else:
                db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) AS n FROM runs").fetchone()["n"] >= capacity:
                raise AdmissionError(
                    "Report storage capacity reached; export/archive with the operator"
                )
            if enforce_submission_limits and (
                db.execute(
                    "SELECT count(*) AS n FROM runs WHERE created_at >= ?", (stamp[:10],)
                ).fetchone()["n"]
                >= daily
            ):
                raise AdmissionError("Daily generation limit reached")
            from datetime import timedelta

            minute_ago = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            if enforce_submission_limits and (
                db.execute(
                    "SELECT count(*) AS n FROM runs WHERE created_at >= ?", (minute_ago,)
                ).fetchone()["n"]
                >= 3
            ):
                raise AdmissionError("At most three submissions per minute")
            run_id = uuid4().hex
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    stamp,
                    stamp,
                    "queued",
                    "queued",
                    request.model_dump_json(),
                    "{}",
                    None,
                    None,
                ),
            )
        return run_id

    def update(self, run_id, *, status=None, stage=None, progress=None, report=None, error=None):
        changes = {"updated_at": now()}
        for k, v in {
            "status": status,
            "stage": stage,
            "progress": progress,
            "report": report,
            "error": error,
        }.items():
            if v is not None:
                changes[k] = (
                    v.model_dump_json()
                    if isinstance(v, Report)
                    else (json.dumps(v) if isinstance(v, dict) else v)
                )
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET " + ",".join(f"{k}=?" for k in changes) + " WHERE id=?",
                [*changes.values(), run_id],
            )

    def get(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ("request", "progress", "report"):
            if result[key] is not None:
                result[key] = json.loads(result[key])
        return result
