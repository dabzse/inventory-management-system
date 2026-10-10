"""SQLite connection, schema migrations, and transaction helpers."""

import sqlite3
from pathlib import Path

MEMORY_DATABASE_PATH = ":memory:"
FOREIGN_KEYS_PRAGMA = "PRAGMA foreign_keys = ON"

BOOTSTRAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS permissions (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS group_permissions (
    group_id INTEGER NOT NULL REFERENCES groups(id),
    permission_id INTEGER NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (group_id, permission_id)
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    password_hash TEXT
);
CREATE TABLE IF NOT EXISTS user_groups (
    user_id INTEGER NOT NULL REFERENCES users(id),
    group_id INTEGER NOT NULL REFERENCES groups(id),
    PRIMARY KEY (user_id, group_id)
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS = (
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        sku TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        reorder_level INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
    );
    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY,
        product_id INTEGER NOT NULL REFERENCES products(id),
        movement_type TEXT NOT NULL CHECK (movement_type IN ('receive', 'issue', 'adjustment')),
        quantity INTEGER NOT NULL,
        previous_quantity INTEGER NOT NULL,
        resulting_quantity INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
    );
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS permissions (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS group_permissions (
        group_id INTEGER NOT NULL REFERENCES groups(id),
        permission_id INTEGER NOT NULL REFERENCES permissions(id),
        PRIMARY KEY (group_id, permission_id)
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
    );
    CREATE TABLE IF NOT EXISTS user_groups (
        user_id INTEGER NOT NULL REFERENCES users(id),
        group_id INTEGER NOT NULL REFERENCES groups(id),
        PRIMARY KEY (user_id, group_id)
    );
    CREATE TABLE IF NOT EXISTS custom_tables (
        id INTEGER PRIMARY KEY,
        table_name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS custom_columns (
        id INTEGER PRIMARY KEY,
        custom_table_id INTEGER NOT NULL REFERENCES custom_tables(id) ON DELETE CASCADE,
        column_name TEXT NOT NULL,
        data_type TEXT NOT NULL,
        is_primary_key INTEGER NOT NULL DEFAULT 0 CHECK (is_primary_key IN (0, 1)),
        foreign_table TEXT,
        foreign_column TEXT,
        position INTEGER NOT NULL,
        UNIQUE (custom_table_id, column_name)
    );
    CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
    CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
    CREATE INDEX IF NOT EXISTS idx_movements_type ON stock_movements(movement_type);
    CREATE INDEX IF NOT EXISTS idx_movements_created_at ON stock_movements(created_at);
    """,
    "ALTER TABLE users ADD COLUMN password_hash TEXT;",
    """
    ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES categories(id);
    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
    """,
    """
    PRAGMA foreign_keys = OFF;
    CREATE TABLE products_new (
        id INTEGER PRIMARY KEY,
        sku TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        reorder_level INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
        category_id INTEGER REFERENCES categories(id)
    );
    INSERT INTO products_new (id, sku, name, quantity, reorder_level, archived, category_id)
    SELECT id, sku, name, quantity, reorder_level, archived, category_id
    FROM products;
    DROP TABLE products;
    ALTER TABLE products_new RENAME TO products;
    CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
    PRAGMA foreign_keys = ON;
    """,
    """
    ALTER TABLE stock_movements ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id);
    ALTER TABLE stock_movements ADD COLUMN customer_id INTEGER REFERENCES customers(id);
    CREATE INDEX IF NOT EXISTS idx_movements_supplier ON stock_movements(supplier_id);
    CREATE INDEX IF NOT EXISTS idx_movements_customer ON stock_movements(customer_id);
    """,
    """
    ALTER TABLE suppliers ADD COLUMN notes TEXT;
    ALTER TABLE customers ADD COLUMN notes TEXT;
    """,
)

SEED_GROUPS = {
    "Administrator": {"product.write", "stock.write", "schema.create", "rbac.manage"},
    "Manager": {"product.write", "stock.write"},
    "Viewer": set(),
}


def initialize_database(path: Path | str) -> sqlite3.Connection:
    """Create the database file if needed, apply migrations, and return an open connection."""
    if path != MEMORY_DATABASE_PATH:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.is_dir():
            raise ValueError(f"Database path is a directory: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(FOREIGN_KEYS_PRAGMA)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_version")}
    if path != MEMORY_DATABASE_PATH and len(applied) < len(MIGRATIONS):
        source_path = Path(path)
        backup_database(
            source_path,
            source_path.with_name(f"{source_path.stem}-pre-migration-backup{source_path.suffix}"),
        )
    for version, migration in enumerate(MIGRATIONS, start=1):
        if version not in applied:
            _apply_migration(connection, version, migration)
            connection.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    _seed_rbac(connection)
    connection.commit()
    return connection


def connect_bootstrap(path: Path | str) -> sqlite3.Connection:
    """Open a minimal auth database until the first inventory import is committed."""
    if path == MEMORY_DATABASE_PATH:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute(FOREIGN_KEYS_PRAGMA)
        connection.executescript(BOOTSTRAP_SCHEMA)
        _seed_rbac(connection)
        connection.commit()
        return connection
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute(FOREIGN_KEYS_PRAGMA)
    has_inventory = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'products'"
    ).fetchone()
    connection.close()
    if has_inventory:
        return initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute(FOREIGN_KEYS_PRAGMA)
    connection.executescript(BOOTSTRAP_SCHEMA)
    _seed_rbac(connection)
    connection.commit()
    return connection


def _apply_migration(connection: sqlite3.Connection, version: int, migration: str) -> None:
    """Apply a migration while tolerating columns added by an interrupted upgrade."""
    if version == 2:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "password_hash" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        return
    if version != 6:
        connection.executescript(migration)
        return
    for table in ("suppliers", "customers"):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "notes" not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN notes TEXT")


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection, apply migrations, and enable foreign keys."""
    return initialize_database(path)


def backup_database(path: Path | str, backup_path: Path | str | None = None) -> Path:
    """Create a copy of an SQLite database at the requested backup path."""
    source_path = Path(path)
    if str(path) == MEMORY_DATABASE_PATH:
        raise ValueError("In-memory databases cannot be backed up to disk.")
    if not source_path.exists():
        raise FileNotFoundError(f"Database does not exist: {source_path}")

    target_path = Path(backup_path) if backup_path is not None else source_path.with_name(
        f"{source_path.stem}-backup{source_path.suffix}"
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(target_path)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
    finally:
        source_connection.close()

    return target_path


def validate_database(path: Path | str) -> None:
    """Raise a clear error when an SQLite database fails an integrity check."""
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Database does not exist: {source_path}")
    try:
        connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Database is not a valid SQLite file: {source_path}") from error
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Database integrity check failed: {source_path}") from error
    finally:
        connection.close()
    if result is None or result[0] != "ok":
        detail = result[0] if result else "no result"
        raise ValueError(f"Database integrity check failed: {detail}")


def _seed_rbac(connection: sqlite3.Connection) -> None:
    """Create the default groups and their permissions once."""
    for group_name, permission_codes in SEED_GROUPS.items():
        connection.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (group_name,))
        group_id = connection.execute(
            "SELECT id FROM groups WHERE name = ?", (group_name,)
        ).fetchone()[0]
        for code in permission_codes:
            connection.execute("INSERT OR IGNORE INTO permissions (code) VALUES (?)", (code,))
            permission_id = connection.execute(
                "SELECT id FROM permissions WHERE code = ?", (code,)
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO group_permissions (group_id, permission_id) VALUES (?, ?)",
                (group_id, permission_id),
            )


class Transaction:
    """Commit a database transaction or roll it back after an exception."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create a transaction wrapper for a SQLite connection."""
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        """Return the wrapped connection to the context block."""
        return self.connection

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        """Commit on success and roll back when the context block fails."""
        if exception_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()


def transaction(connection: sqlite3.Connection) -> Transaction:
    """Return a transaction context manager for the connection."""
    return Transaction(connection)
