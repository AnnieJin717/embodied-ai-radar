"""PostgreSQL connection for the same admin tables used in the local SQLite database."""
from contextlib import contextmanager
import psycopg


class Record(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def records(cursor):
    names = [column.name for column in cursor.description or ()]
    return lambda values: Record(zip(names, values))


class Database:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        # All statements come from the application's fixed queries.
        if sql.strip() == "BEGIN IMMEDIATE":
            return self.conn.execute("SELECT pg_advisory_xact_lock(718001)")
        sql = sql.replace("?", "%s")
        return self.conn.execute(sql, args)

    def executemany(self, sql, rows):
        with self.conn.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), rows)

    def executescript(self, sql):
        for statement in sql.split(";"):
            if statement.strip():
                statement = statement.replace("INTEGER PRIMARY KEY", "BIGSERIAL PRIMARY KEY")
                statement = statement.replace("DEFAULT CURRENT_TIMESTAMP","DEFAULT (CURRENT_TIMESTAMP::text)")
                self.conn.execute(statement)


@contextmanager
def connection(url):
    with psycopg.connect(url, row_factory=records, connect_timeout=10) as conn:
        yield Database(conn)
