"""Compatibility for the repository's parameterized SQL on psycopg 3."""

class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


class Connection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, sql, params=()):
        # All repository placeholders are outside string literals; no user SQL is accepted.
        return self.raw.execute(sql.replace('%', '%%').replace('?', '%s'), params)


def initialize(connection, base, extension):
    ddl = base.replace('PRAGMA journal_mode=WAL;', '').replace(
        'INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY').replace(
        'INSERT OR IGNORE INTO schema_version VALUES (1);',
        'INSERT INTO schema_version VALUES (1) ON CONFLICT DO NOTHING;')
    for statement in (ddl + extension).split(';'):
        if statement.strip():
            connection.execute(statement)
