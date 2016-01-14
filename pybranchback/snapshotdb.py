import contextlib
import sqlite3


CREATE = """
    CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        hash TEXT NOT NULL,
        branch TEXT NOT NULL,
        label TEXT,
        message TEXT,
        user TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
"""
INSERT = """
    INSERT INTO snapshots (hash, branch, label, message, user)
    VALUES (:hash, :branch, :label, :message, :user)
"""
SELECT = """SELECT * FROM snapshots"""

# Alias sqlite3.Row
Row = sqlite3.Row


def execute(db_path, command, row_factory=None):
    with contextlib.closing(sqlite3.connect(db_path)) as con:
        if row_factory is not None:
            con.row_factory = row_factory
        with contextlib.closing(con.cursor()) as cur:
            return cur.execute(command)
