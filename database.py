"""
database.py
Database connection and schema for the web version of the Student
Management System.

Two modes, chosen automatically:
- If a DATABASE_URL environment variable is set (Render's free
  PostgreSQL provides this automatically once attached), connects to
  that PostgreSQL database. Data persists permanently.
- Otherwise, falls back to a local SQLite file (school.db) — handy for
  running on your own machine, but NOT persistent on most free hosts,
  since their filesystem resets on every redeploy/restart.

Everywhere else in the app (app.py, auth.py) calls get_connection()
and then uses conn.execute(sql, params).fetchone()/.fetchall(), exactly
like Python's built-in sqlite3 module. A small wrapper class below makes
psycopg2 (PostgreSQL) behave the same way, so nothing else in the app
needs to know or care which database is actually in use.
"""

import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")
USING_POSTGRES = bool(DATABASE_URL)

if USING_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # Render (and some other hosts) hand out a URL starting with
    # "postgres://", but psycopg2 requires "postgresql://".
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "school.db")


class _PGCursorWrapper:
    """Makes a psycopg2 cursor look like a sqlite3 cursor for our purposes:
    .fetchone()/.fetchall() work the same, and .lastrowid gives the new
    row's id right after an INSERT (via an auto-added RETURNING id)."""

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PGConnectionWrapper:
    """Wraps a psycopg2 connection so the rest of the app can call
    conn.execute(sql, params) exactly like it would on sqlite3 — same
    '?' placeholders, same dict-like rows, same .lastrowid after an
    INSERT — without needing to know Postgres is underneath."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=()):
        pg_sql = sql.replace("?", "%s")
        is_insert = pg_sql.strip().upper().startswith("INSERT") and "RETURNING" not in pg_sql.upper()
        if is_insert:
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params)
        lastrowid = None
        if is_insert:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None
        return _PGCursorWrapper(cur, lastrowid)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_connection():
    if USING_POSTGRES:
        pg_conn = psycopg2.connect(DATABASE_URL)
        return _PGConnectionWrapper(pg_conn)
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    if USING_POSTGRES:
        id_col = "id SERIAL PRIMARY KEY"
        ts_col = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    else:
        id_col = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        ts_col = "TEXT DEFAULT CURRENT_TIMESTAMP"

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            {id_col},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'teacher', 'student')),
            full_name TEXT NOT NULL,
            email TEXT,
            created_at {ts_col}
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS teachers (
            {id_col},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject TEXT,
            phone TEXT
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS classes (
            {id_col},
            class_name TEXT NOT NULL,
            section TEXT,
            teacher_id INTEGER REFERENCES teachers(id)
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS students (
            {id_col},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            roll_no TEXT UNIQUE,
            class_id INTEGER REFERENCES classes(id),
            phone TEXT,
            dob TEXT,
            enrollment_date {ts_col}
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS courses (
            {id_col},
            course_name TEXT NOT NULL,
            course_code TEXT UNIQUE,
            class_id INTEGER REFERENCES classes(id)
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS attendance (
            {id_col},
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            class_id INTEGER NOT NULL REFERENCES classes(id),
            date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Late')),
            UNIQUE(student_id, date)
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS marks (
            {id_col},
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id),
            exam_type TEXT NOT NULL,
            marks_obtained REAL NOT NULL,
            max_marks REAL NOT NULL,
            date {ts_col}
        )
    """)

    # Seed default admin: admin / admin123 (only if no admin exists yet)
    existing = conn.execute("SELECT id FROM users WHERE role='admin'").fetchone()
    if not existing:
        from werkzeug.security import generate_password_hash
        conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?,?,?,?,?)",
            ("admin", generate_password_hash("admin123"), "admin", "Super Admin", "admin@school.com")
        )

    conn.commit()
    conn.close()
