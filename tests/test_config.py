"""Tests for development and packaged application paths."""

import sys
from pathlib import Path

import pytest

from ims import config
from ims.database.connection import backup_database, initialize_database, validate_database


def test_development_data_dir_stays_project_local() -> None:
    """Source runs continue using the project database directory."""
    assert config.application_data_dir() == config.PROJECT_ROOT / "database"


def test_frozen_linux_data_dir_uses_xdg_data_home(monkeypatch, tmp_path) -> None:
    """Frozen Linux builds store data under the user's writable data directory."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert config.application_data_dir("posix", "linux") == tmp_path / "data" / "ims"


def test_frozen_windows_data_dir_uses_appdata(monkeypatch, tmp_path) -> None:
    """Frozen Windows builds use the roaming application-data directory."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    assert config.application_data_dir("nt", "win32") == tmp_path / "roaming" / "IMS"


def test_database_path_supports_shared_location(tmp_path) -> None:
    """Shared mode resolves the explicitly configured database path."""
    settings_path = tmp_path / "settings.ini"
    settings_path.write_text(
        "[database]\ndatabase_location = shared\ndatabase_path = ~/shared/inventory.sqlite3\n",
        encoding="utf-8",
    )

    assert config.database_path(settings_path) == Path.home() / "shared" / "inventory.sqlite3"


def test_database_path_rejects_invalid_shared_configuration(tmp_path) -> None:
    """Shared mode requires a database path and rejects unknown modes."""
    settings_path = tmp_path / "settings.ini"
    settings_path.write_text("[database]\ndatabase_location = shared\n", encoding="utf-8")

    with pytest.raises(ValueError, match="database_path"):
        config.database_path(settings_path)

    settings_path.write_text("[database]\ndatabase_location = remote\n", encoding="utf-8")
    with pytest.raises(ValueError, match="local.*shared"):
        config.database_path(settings_path)


def test_configured_database_supports_migration_backup_and_restore(tmp_path) -> None:
    """A configured packaged path supports the complete database lifecycle."""
    settings_path = tmp_path / "settings.ini"
    database_file = tmp_path / "shared" / "inventory.sqlite3"
    settings_path.write_text(
        "[database]\ndatabase_location = shared\n"
        f"database_path = {database_file}\n",
        encoding="utf-8",
    )

    configured_path = config.database_path(settings_path)
    connection = initialize_database(configured_path)
    connection.close()
    backup_file = backup_database(configured_path, tmp_path / "backup.sqlite3")
    restore_file = tmp_path / "restored.sqlite3"
    backup_database(backup_file, restore_file)

    validate_database(restore_file)
    restored = initialize_database(restore_file)
    try:
        assert restored.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] > 0
    finally:
        restored.close()
