"""Application entry point for the inventory management desktop app."""

import importlib
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ims.config import APP_DATA_DIR, DATABASE_PATH, configure_logging
from ims.database.connection import connect, connect_bootstrap
from ims.repositories.products import ProductRepository
from ims.services.settings import SettingsService
from ims.services.stock import StockService
from ims.ui.dialogs import LoginDialog, UserDialog
from ims.ui.export_worker import BackupWorker
from ims.ui.main_window import MainWindow

QtWidgets = importlib.import_module("PySide6.QtWidgets")
QtCore = importlib.import_module("PySide6.QtCore")


def _schedule_backups(
    application: Any, database_path: Path, settings: SettingsService, logger: Any
) -> Any:
    """Schedule timestamped database backups when the setting is enabled."""
    interval_hours = settings.backup_interval_hours()
    if interval_hours <= 0:
        return None
    timer = QtCore.QTimer(application)
    timer.setInterval(interval_hours * 60 * 60 * 1000)
    backup_threads: list[Any] = []

    def create_backup() -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        destination = APP_DATA_DIR / "backups" / f"{database_path.stem}-{timestamp}.sqlite3"
        thread = QtCore.QThread(application)
        worker = BackupWorker(database_path, destination)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda _: logger.info("scheduled_backup_completed"))
        worker.failed.connect(
            lambda _: logger.warning("scheduled_backup_failed", extra={"error_type": "backup"})
        )
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: backup_threads.remove(thread))
        backup_threads.append(thread)
        thread.start()

    timer.timeout.connect(create_backup)
    timer.start()
    return timer


def main() -> None:
    """Start the inventory management desktop application."""
    logger = configure_logging()
    logger.info("application_starting")
    application = QtWidgets.QApplication(sys.argv)
    try:
        connection = connect_bootstrap(DATABASE_PATH)
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'products'"
        ).fetchone() is None:
            connection.close()
            connection = connect(DATABASE_PATH)
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        logger.warning("database_open_failed", extra={"error_type": type(error).__name__})
        QtWidgets.QMessageBox.critical(
            None,
            "Database error",
            f"The inventory database could not be opened.\n\n{error}",
        )
        raise SystemExit(1) from error
    if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        setup = UserDialog(connection, setup=True)
        if setup.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            connection.close()
            raise SystemExit(0)
    login = LoginDialog(connection)
    if login.exec() != QtWidgets.QDialog.DialogCode.Accepted or login.session is None:
        connection.close()
        raise SystemExit(0)
    products = ProductRepository(connection)
    settings = SettingsService(connection)
    backup_timer = _schedule_backups(application, DATABASE_PATH, settings, logger)
    window = MainWindow(products, StockService(connection), login.session)
    window.show()
    exit_code = application.exec()
    if backup_timer is not None:
        backup_timer.stop()
    connection.close()
    logger.info("application_stopped")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
