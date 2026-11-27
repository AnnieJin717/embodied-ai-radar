"""Restore a downloaded full backup into a new local SQLite file."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from .admin.backup import TABLES

def restore(source,destination):
    if not source.is_file():
        raise ValueError("Backup file not found.")
    with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("Backup failed its integrity check.")
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(TABLES)<=names:
            raise ValueError("Incomplete backup.")
        # Create exclusively so an existing local database can never be overwritten.
        with destination.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destination)) as target:
                db.backup(target)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup",type=Path)
    parser.add_argument("new_file",type=Path)
    args=parser.parse_args()
    restore(args.backup,args.new_file)
