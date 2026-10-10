"""Tests for persisted runtime settings."""

from ims.database.connection import connect
from ims.services.settings import SettingsService


def test_backup_interval_setting_defaults_to_disabled() -> None:
    """Scheduled backups remain opt-in for new databases."""
    settings = SettingsService(connect(":memory:"))

    assert settings.backup_interval_hours() == 0


def test_backup_interval_setting_accepts_positive_hours_and_rejects_invalid_values() -> None:
    """The backup interval is stored as an integer and invalid values disable scheduling."""
    connection = connect(":memory:")
    settings = SettingsService(connection)

    settings.set("backup_interval_hours", 24)
    assert settings.backup_interval_hours() == 24

    settings.set("backup_interval_hours", "not-a-number")
    assert settings.backup_interval_hours() == 0

    settings.set("backup_interval_hours", -4)
    assert settings.backup_interval_hours() == 0
