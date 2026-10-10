"""Background workers for file exports that do not require database access."""

import csv
import html
import importlib
from pathlib import Path

from ims.database.connection import backup_database

QtCore = importlib.import_module("PySide6.QtCore")
QtGui = importlib.import_module("PySide6.QtGui")
QtPrintSupport = importlib.import_module("PySide6.QtPrintSupport")


class CsvExportWorker(QtCore.QObject):
    """Write a prepared tabular export without blocking the Qt event loop."""

    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(
        self, path: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]
    ) -> None:
        super().__init__()
        self.path = path
        self.headers = headers
        self.rows = rows

    @QtCore.Slot()
    def run(self) -> None:
        """Write the export and notify the owning dialog of the result."""
        try:
            destination = Path(self.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", newline="", encoding="utf-8") as export_file:
                writer = csv.writer(export_file)
                writer.writerow(self.headers)
                writer.writerows(self.rows)
        except (OSError, csv.Error) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(self.path)


class PdfExportWorker(QtCore.QObject):
    """Render prepared report rows to PDF without blocking the Qt event loop."""

    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        path: str,
        title: str,
        headers: tuple[str, ...],
        rows: list[tuple[str, ...]],
    ) -> None:
        super().__init__()
        self.path = path
        self.title = title
        self.headers = headers
        self.rows = rows

    @QtCore.Slot()
    def run(self) -> None:
        """Render the prepared report and notify the owning window."""
        try:
            header_html = "".join(f"<th>{html.escape(header)}</th>" for header in self.headers)
            rows_html = "".join(
                "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
                for row in self.rows
            )
            document = QtGui.QTextDocument()
            document.setHtml(
                f"<h1>{html.escape(self.title)}</h1>"
                f"<table border='1' cellspacing='0' cellpadding='4'>"
                f"<tr>{header_html}</tr>{rows_html}</table>"
            )
            printer = QtPrintSupport.QPrinter(
                QtPrintSupport.QPrinter.PrinterMode.HighResolution
            )
            printer.setOutputFormat(QtPrintSupport.QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(self.path)
            document.print_(printer)
        except (OSError, RuntimeError) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(self.path)


class BackupWorker(QtCore.QObject):
    """Create a database backup without blocking the Qt event loop."""

    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, source: Path, destination: Path) -> None:
        super().__init__()
        self.source = source
        self.destination = destination

    @QtCore.Slot()
    def run(self) -> None:
        """Create the backup and notify the application of the result."""
        try:
            backup_database(self.source, self.destination)
        except (OSError, RuntimeError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(str(self.destination))
