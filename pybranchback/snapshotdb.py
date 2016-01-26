import contextlib
import sqlite3


CREATE = """
    CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        hash TEXT NOT NULL,
        branch TEXT NOT NULL,
        message TEXT,
        user TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
"""
INSERT = """
    INSERT INTO snapshots (hash, branch, message, user)
    VALUES (:hash, :branch, :message, :user)
"""
SELECT = """SELECT * FROM snapshots"""

# Alias sqlite3.Row
Row = sqlite3.Row


def execute(
        db_path, command, parameters=None,
        row_factory=None, commit=False, cursor=''):
    if parameters is None:
        parameters = {}
    with contextlib.closing(sqlite3.connect(db_path)) as con:
        if row_factory is not None:
            con.row_factory = row_factory
        with contextlib.closing(con.cursor()) as cur:
            cur.execute(command, parameters)
            if commit:
                con.commit()
            if cursor:
                return getattr(cur, cursor)()
