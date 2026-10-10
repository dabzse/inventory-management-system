"""Validated creation of user-defined SQLite tables."""

import re
import sqlite3
from dataclasses import dataclass

IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$", re.ASCII)
DATA_TYPES = {"TEXT", "INTEGER", "REAL", "NUMERIC"}


@dataclass(frozen=True)
class ColumnDefinition:
    """Describe one user-defined table column."""

    name: str
    data_type: str
    primary_key: bool = False
    foreign_table: str | None = None
    foreign_column: str | None = None


def _identifier(value: str, label: str) -> str:
    value = value.strip()
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must contain only letters, numbers, and underscores")
    return value


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
    ).fetchone() is not None


def _normalize_column(
    connection: sqlite3.Connection, column: ColumnDefinition
) -> tuple[str, ColumnDefinition]:
    """Validate one column and build its SQL definition."""
    name = _identifier(column.name, "Column name")
    data_type = column.data_type.upper()
    if data_type not in DATA_TYPES:
        raise ValueError("Unsupported column type")
    foreign_table = column.foreign_table
    foreign_column = column.foreign_column
    definition = f'"{name}" {data_type}'
    if column.primary_key:
        definition += " PRIMARY KEY"
    if foreign_table or foreign_column:
        if not foreign_table or not foreign_column:
            raise ValueError("Foreign keys require both a table and column")
        foreign_table = _identifier(foreign_table, "Foreign table")
        foreign_column = _identifier(foreign_column, "Foreign column")
        if not _table_exists(connection, foreign_table):
            raise ValueError("Foreign-key table does not exist")
        foreign_columns = {
            row[1] for row in connection.execute(f'PRAGMA table_info("{foreign_table}")')
        }
        if foreign_column not in foreign_columns:
            raise ValueError("Foreign-key column does not exist")
        definition += f' REFERENCES "{foreign_table}"("{foreign_column}")'
    normalized = ColumnDefinition(name, data_type, column.primary_key, foreign_table, foreign_column)
    return definition, normalized


def _normalize_columns(
    connection: sqlite3.Connection, columns: list[ColumnDefinition]
) -> tuple[list[str], list[ColumnDefinition]]:
    """Validate columns and return SQL definitions plus normalized metadata."""
    if not columns or len(columns) > 20:
        raise ValueError("Add between one and twenty columns")
    if sum(column.primary_key for column in columns) > 1:
        raise ValueError("Only one primary-key column is supported")
    definitions: list[str] = []
    normalized: list[ColumnDefinition] = []
    names: set[str] = set()
    for column in columns:
        definition, normalized_column = _normalize_column(connection, column)
        name = normalized_column.name
        if name in names:
            raise ValueError("Column names must be unique")
        names.add(name)
        definitions.append(definition)
        normalized.append(normalized_column)
    return definitions, normalized


def create_custom_table(
    connection: sqlite3.Connection, table_name: str, columns: list[ColumnDefinition]
) -> None:
    """Create a custom table and persist its column metadata atomically."""
    table_name = _identifier(table_name, "Table name")
    if table_name.startswith("sqlite_") or _table_exists(connection, table_name):
        raise ValueError("That table name is unavailable")
    definitions, normalized = _normalize_columns(connection, columns)

    with connection:
        connection.execute(f'CREATE TABLE "{table_name}" ({", ".join(definitions)})')
        cursor = connection.execute(
            "INSERT INTO custom_tables (table_name) VALUES (?)", (table_name,)
        )
        for position, column in enumerate(normalized):
            connection.execute(
                "INSERT INTO custom_columns "
                "(custom_table_id, column_name, data_type, is_primary_key, "
                "foreign_table, foreign_column, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cursor.lastrowid,
                    column.name,
                    column.data_type,
                    int(column.primary_key),
                    column.foreign_table,
                    column.foreign_column,
                    position,
                ),
            )
