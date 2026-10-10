"""Application paths and runtime configuration."""

import json
import logging
import os
import sys
from configparser import ConfigParser
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = (
    Path(sys.executable).resolve().with_name("settings.ini")
    if getattr(sys, "frozen", False)
    else PROJECT_ROOT / "settings.ini"
)


def application_data_dir(
    system_name: str | None = None, platform_name: str | None = None
) -> Path:
    """Return the writable application data directory for the current runtime."""
    system_name = os.name if system_name is None else system_name
    platform_name = sys.platform if platform_name is None else platform_name
    if not getattr(sys, "frozen", False):
        return PROJECT_ROOT / "database"
    if system_name == "nt":
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base_dir / "IMS"
    if platform_name == "darwin":
        return Path.home() / "Library" / "Application Support" / "IMS"
    base_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base_dir / "ims"


APP_DATA_DIR = application_data_dir()


def database_path(settings_path: Path | str = SETTINGS_PATH) -> Path:
    """Resolve the database path from local or shared INI configuration."""
    parser = ConfigParser()
    parser.read(settings_path, encoding="utf-8")
    location = parser.get("database", "database_location", fallback="local").strip().lower()
    if location == "local":
        return APP_DATA_DIR / "inventory.sqlite3"
    if location == "shared":
        shared_path = parser.get("database", "database_path", fallback="").strip()
        if not shared_path:
            raise ValueError("Shared database mode requires database_path in settings.ini")
        return Path(shared_path).expanduser()
    raise ValueError("database_location must be either 'local' or 'shared'")


def google_sheets_settings(settings_path: Path | str = SETTINGS_PATH) -> tuple[str, str]:
    """Return the optional service-account path and spreadsheet URL or ID."""
    parser = ConfigParser()
    parser.read(settings_path, encoding="utf-8")
    return (
        parser.get("google_sheets", "credentials_file", fallback="").strip(),
        parser.get("google_sheets", "spreadsheet_url", fallback="").strip(),
    )


DATABASE_PATH = database_path()
LOG_PATH = APP_DATA_DIR / "ims.log"


class JsonFormatter(logging.Formatter):
    """Format application events as one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize safe event fields without including message arguments."""
        return json.dumps(
            {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
            },
            separators=(",", ":"),
        )


def configure_logging() -> logging.Logger:
    """Configure rotating application logging and return the app logger."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ims")
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
