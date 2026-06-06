SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_CONNECT_PRAGMAS = (
    f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=20000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=134217728",
)


def configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for statement in SQLITE_CONNECT_PRAGMAS:
            cursor.execute(statement)
    finally:
        cursor.close()
