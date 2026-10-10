"""Database-backed application settings for runtime inventory behavior."""

import sqlite3

NEGATIVE_STOCK_KEY = "negative_stock_enabled"
DATABASE_PATH_KEY = "database_path"
BACKUP_INTERVAL_HOURS_KEY = "backup_interval_hours"


class SettingsService:
    """Read and write persisted application settings."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create a settings service backed by the supplied SQLite connection."""
        self.connection = connection

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the configured value for a key, or the provided default."""
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set(self, key: str, value: str | bool | int) -> str:
        """Persist a scalar setting while returning the stored string value."""
        stored = str(value)
        self.connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, stored),
        )
        self.connection.commit()
        return stored

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean setting as a Python bool, coercing common string values."""
        value = self.get(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def get_int(self, key: str, default: int = 0) -> int:
        """Return an integer setting, falling back when it is missing or invalid."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def backup_interval_hours(self) -> int:
        """Return the scheduled backup interval, or zero when scheduling is disabled."""
        return max(0, self.get_int(BACKUP_INTERVAL_HOURS_KEY, default=0))

    def set_bool(self, key: str, value: bool) -> bool:
        """Persist a boolean setting in a SQLite-friendly format."""
        self.set(key, "1" if value else "0")
        return value

    def is_negative_stock_enabled(self) -> bool:
        """Return whether issuing or adjusting below zero is allowed."""
        return self.get_bool(NEGATIVE_STOCK_KEY, default=False)

    def set_negative_stock_enabled(self, enabled: bool) -> bool:
        """Persist the negative-stock policy for this database."""
        return self.set_bool(NEGATIVE_STOCK_KEY, enabled)

    def get_database_path(self, default: str | None = None) -> str | None:
        """Return the configured data-path, if any."""
        return self.get(DATABASE_PATH_KEY, default)

    def set_database_path(self, path: str) -> str:
        """Persist the application database path."""
        return self.set(DATABASE_PATH_KEY, path)
