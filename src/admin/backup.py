"""Portable, consistent SQLite download for both storage backends."""
import sqlite3
from . import store
from .publication import initialize

TABLES = ("extractions","reviews","companies","events","edits","candidates","editions")

def download(db):
    if isinstance(db,sqlite3.Connection):
        with sqlite3.connect(":memory:") as target:
            db.backup(target)
            return target.serialize()
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    with sqlite3.connect(":memory:") as target:
        target.row_factory=sqlite3.Row
        store.initialize(target)
        target.commit()
        initialize(target)
        for table in TABLES:
            target.execute("DELETE FROM "+table)
            rows=db.execute("SELECT * FROM "+table)
            for row in rows:
                slots=",".join("?" for _ in row)
                target.execute(f"INSERT INTO {table} VALUES ({slots})",tuple(row.values()))
        target.commit()
        return target.serialize()
