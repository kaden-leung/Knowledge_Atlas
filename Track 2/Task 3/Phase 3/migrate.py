"""Minimal idempotent SQLite migration runner for Phase 3.

Why we ship our own:
- `Article_Finder/core/schema_registry.py` is tied to `article_finder.db` and
  assumes the AF schema is already present. Phase 3 stands up its own DB.
- A 40-line runner is easier to audit than a vendored framework.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_MIGRATIONS_DIR = _HERE / "migrations"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _schema_versions (
            filename    TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL
        )
        """
    )


def apply_migrations(
    db_path: Path | str,
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
) -> list[str]:
    """Apply every `*.sql` in `migrations_dir` in lexicographic order, idempotently.

    Returns the list of newly applied filenames (empty = no-op).
    """
    db_path = Path(db_path)
    migrations_dir = Path(migrations_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_meta_table(conn)

        already = {
            row[0]
            for row in conn.execute("SELECT filename FROM _schema_versions").fetchall()
        }

        applied: list[str] = []
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            if sql_file.name in already:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            # Strip inline -- comments before splitting so that a semicolon
            # inside a comment (e.g. "-- soft FK; not enforced") does not
            # break the statement boundary detection.
            sql_stripped = re.sub(r"--[^\n]*", "", sql)
            with conn:
                for stmt in sql_stripped.split(";"):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as exc:
                        msg = str(exc).lower()
                        if "duplicate column" in msg or "already exists" in msg:
                            continue  # idempotent — column already added
                        raise
                conn.execute(
                    "INSERT INTO _schema_versions(filename, applied_at) VALUES (?, ?)",
                    (sql_file.name, _utc_now_iso()),
                )
            applied.append(sql_file.name)
        return applied
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Phase 3 migration runner")
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database (created if missing)",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(DEFAULT_MIGRATIONS_DIR),
        help="Directory containing *.sql files",
    )
    args = parser.parse_args(argv)

    applied = apply_migrations(args.db, args.migrations_dir)
    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for name in applied:
            print(f"  - {name}")
    else:
        print("No new migrations to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
