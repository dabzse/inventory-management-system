"""Tests for database initialization, RBAC seeds, and custom tables."""

import sqlite3

import pytest

from ims.database.connection import (
    MIGRATIONS,
    backup_database,
    connect,
    connect_bootstrap,
    initialize_database,
    validate_database,
)
from ims.services.access import has_permission, list_groups
from ims.services.schema import ColumnDefinition, create_custom_table


def test_connection_seeds_three_groups_and_permissions() -> None:
    """A fresh database contains the initial RBAC groups."""
    connection = connect(":memory:")

    assert list_groups(connection) == ["Administrator", "Manager", "Viewer"]
    assert has_permission(connection, "Administrator", "schema.create")
    assert not has_permission(connection, "Viewer", "schema.create")


def test_bootstrap_database_contains_auth_tables_without_inventory_tables() -> None:
    """New installations begin with authentication tables only."""
    connection = connect_bootstrap(":memory:")

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"users", "groups", "permissions", "settings"} <= tables
    assert "products" not in tables


def test_custom_table_records_columns_and_foreign_key() -> None:
    """Custom tables support a primary key and a validated foreign key."""
    connection = connect(":memory:")
    create_custom_table(
        connection,
        "locations",
        [ColumnDefinition("id", "INTEGER", primary_key=True)],
    )
    create_custom_table(
        connection,
        "bins",
        [
            ColumnDefinition("id", "INTEGER", primary_key=True),
            ColumnDefinition("location_id", "INTEGER", foreign_table="locations", foreign_column="id"),
        ],
    )

    foreign_keys = connection.execute('PRAGMA foreign_key_list("bins")').fetchall()
    metadata = connection.execute(
        "SELECT COUNT(*) FROM custom_columns WHERE custom_table_id = "
        "(SELECT id FROM custom_tables WHERE table_name = 'bins')"
    ).fetchone()[0]
    assert foreign_keys[0][2:] == ("locations", "location_id", "id", "NO ACTION", "NO ACTION", "NONE")
    assert metadata == 2


def test_custom_table_rejects_unsafe_identifiers() -> None:
    """Table and column identifiers cannot inject SQL."""
    connection = connect(":memory:")

    unsafe_name = "bad; DROP TABLE products"
    columns = [ColumnDefinition("id", "INTEGER")]
    with pytest.raises(ValueError, match="Table name"):
        create_custom_table(connection, unsafe_name, columns)


def test_database_helpers_initialize_and_backup_database(tmp_path) -> None:
    """The database helper API creates a database file and a valid backup copy."""
    db_path = tmp_path / "inventory.sqlite3"
    backup_path = tmp_path / "backups" / "inventory-backup.sqlite3"

    connection = initialize_database(db_path)
    try:
        assert db_path.exists()
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 0
        backup_file = backup_database(db_path, backup_path)
        assert backup_file == backup_path
        assert backup_file.exists()
        with sqlite3.connect(backup_file) as backup_connection:
            assert backup_connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        validate_database(backup_file)
    finally:
        connection.close()


def test_validate_database_rejects_invalid_sqlite_file(tmp_path) -> None:
    """Invalid backup content produces a clear validation error."""
    invalid_path = tmp_path / "invalid.sqlite3"
    invalid_path.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(ValueError, match="valid SQLite file|integrity check failed"):
        validate_database(invalid_path)


def test_database_migrates_from_schema_version_four(tmp_path) -> None:
    """The current initializer applies the notes migration to an older database."""
    db_path = tmp_path / "older.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    for version, migration in enumerate(MIGRATIONS[:4], start=1):
        connection.executescript(migration)
        connection.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    connection.commit()
    connection.close()

    migrated = initialize_database(db_path)
    try:
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(suppliers)").fetchall()
        }
        assert "notes" in columns
        assert migrated.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == len(
            MIGRATIONS
        )
    finally:
        migrated.close()


def test_database_initialization_backups_existing_file_before_migrations(tmp_path) -> None:
    """Pending migrations create a backup beside an existing database file."""
    db_path = tmp_path / "inventory.sqlite3"
    db_path.touch()

    connection = initialize_database(db_path)
    connection.close()

    backup_path = tmp_path / "inventory-pre-migration-backup.sqlite3"
    assert backup_path.exists()


def test_database_migration_accepts_notes_columns_from_partial_upgrade(tmp_path) -> None:
    """A partially applied notes migration can finish without a duplicate-column error."""
    db_path = tmp_path / "partial.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    for version, migration in enumerate(MIGRATIONS[:5], start=1):
        connection.executescript(migration)
        connection.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    connection.execute("ALTER TABLE suppliers ADD COLUMN notes TEXT")
    connection.execute("ALTER TABLE customers ADD COLUMN notes TEXT")
    connection.commit()
    connection.close()

    migrated = initialize_database(db_path)
    try:
        assert migrated.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == len(
            MIGRATIONS
        )
    finally:
        migrated.close()
