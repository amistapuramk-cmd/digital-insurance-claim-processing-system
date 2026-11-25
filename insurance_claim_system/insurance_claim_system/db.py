import sqlite3
from flask import g
from werkzeug.security import generate_password_hash

DATABASE = "claims.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'customer'   -- customer | adjuster
);
CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_number TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    policy_type TEXT NOT NULL,              -- Health | Auto | Home | Life
    coverage_amount REAL NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_number TEXT UNIQUE NOT NULL,
    policy_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    incident_date TEXT NOT NULL,
    description TEXT NOT NULL,
    claim_amount REAL NOT NULL,
    approved_amount REAL DEFAULT 0,
    status TEXT NOT NULL,                   -- Submitted | Under Review | Approved | Rejected
    flag_reason TEXT,
    document TEXT,
    adjuster_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (policy_id) REFERENCES policies(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS claim_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM users WHERE username='adjuster'").fetchone():
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,?)",
            ("adjuster", "Default Adjuster", generate_password_hash("admin123"), "adjuster"),
        )
    db.commit()
    db.close()
