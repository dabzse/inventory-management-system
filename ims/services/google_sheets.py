"""Google Sheets access and staged cell-level synchronization."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass(frozen=True)
class SheetTable:
    """A rectangular snapshot from one spreadsheet tab."""

    title: str
    values: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class SheetChange:
    """One staged cell change identified by tab and zero-based coordinates."""

    title: str
    row: int
    column: int
    old_value: str
    new_value: str


class GoogleSheetsError(RuntimeError):
    """Raised when a spreadsheet cannot be read or updated."""


def spreadsheet_id_from_url(value: str) -> str:
    """Extract a spreadsheet ID from a Google Sheets URL or return a raw ID."""
    value = value.strip()
    if not value:
        raise ValueError("Spreadsheet URL or ID is required")
    path_parts = [part for part in urlparse(value).path.split("/") if part]
    if "d" in path_parts:
        document_index = path_parts.index("d")
        if document_index + 1 < len(path_parts):
            return path_parts[document_index + 1]
    if value.startswith(("http://", "https://")):
        raise ValueError("The Google Sheets URL does not contain a spreadsheet ID")
    return value


class GoogleSheetsClient:
    """Read and update all tabs in a Google spreadsheet."""

    def __init__(self, service: Any) -> None:
        """Create a client from an authenticated Google Sheets API service."""
        self.service = service

    @classmethod
    def from_service_account(cls, credentials_path: Path | str) -> "GoogleSheetsClient":
        """Create an authenticated client from a service-account JSON file."""
        try:
            credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
            return cls(build("sheets", "v4", credentials=credentials, cache_discovery=False))
        except (OSError, ValueError) as error:
            raise GoogleSheetsError(f"Could not load Google Sheets credentials: {error}") from error

    def read_all_tabs(self, spreadsheet_id: str) -> tuple[SheetTable, ...]:
        """Read every tab as a rectangular string table, preserving tab order."""
        spreadsheet_id = spreadsheet_id_from_url(spreadsheet_id)
        try:
            metadata = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,index))",
            ).execute()
            sheets = sorted(
                metadata.get("sheets", []),
                key=lambda sheet: sheet.get("properties", {}).get("index", 0),
            )
            ranges = [_quoted_title(sheet["properties"]["title"]) for sheet in sheets]
            response = self.service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=ranges,
                majorDimension="ROWS",
            ).execute()
            value_ranges = response.get("valueRanges", [])
            return tuple(
                SheetTable(
                    sheet["properties"]["title"],
                    _normalize_values(value_range.get("values", [])),
                )
                for sheet, value_range in zip(sheets, value_ranges)
            )
        except Exception as error:
            raise GoogleSheetsError(f"Could not read Google Sheets data: {error}") from error

    def commit(self, spreadsheet_id: str, changes: list[SheetChange]) -> None:
        """Write staged cell changes to the spreadsheet in one batch request."""
        if not changes:
            return
        spreadsheet_id = spreadsheet_id_from_url(spreadsheet_id)
        data = [
            {
                "range": f"{_quoted_title(change.title)}!{_column_name(change.column)}{change.row + 1}",
                "majorDimension": "ROWS",
                "values": [[change.new_value]],
            }
            for change in changes
        ]
        try:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
        except Exception as error:
            raise GoogleSheetsError(f"Could not commit Google Sheets changes: {error}") from error


def diff_tables(original: tuple[SheetTable, ...], current: tuple[SheetTable, ...]) -> list[SheetChange]:
    """Return cell changes between two tab-aware snapshots."""
    original_by_title = {table.title: table for table in original}
    return [
        change
        for current_table in current
        for change in _table_changes(
            original_by_title.get(current_table.title),
            current_table,
        )
    ]


def _table_changes(original: SheetTable | None, current: SheetTable) -> list[SheetChange]:
    """Return changes for one tab."""
    original_values = original.values if original is not None else ()
    row_count = max(len(original_values), len(current.values))
    return [
        change
        for row in range(row_count)
        for change in _row_changes(
            current.title,
            row,
            _row_values(original_values, row),
            _row_values(current.values, row),
        )
    ]


def _row_changes(
    title: str,
    row: int,
    original: tuple[str, ...],
    current: tuple[str, ...],
) -> list[SheetChange]:
    """Return changed cells for one row."""
    column_count = max(len(original), len(current))
    return [
        SheetChange(title, row, column, old_value, new_value)
        for column in range(column_count)
        for old_value, new_value in [(_cell_value(original, column), _cell_value(current, column))]
        if old_value != new_value
    ]


def _row_values(values: tuple[tuple[str, ...], ...], row: int) -> tuple[str, ...]:
    """Return a row or an empty row when the requested row is absent."""
    return values[row] if row < len(values) else ()


def _cell_value(values: tuple[str, ...], column: int) -> str:
    """Return a cell or an empty value when the requested column is absent."""
    return values[column] if column < len(values) else ""


def _normalize_values(values: list[list[Any]]) -> tuple[tuple[str, ...], ...]:
    """Convert API cell values into stable string values for editing and comparison."""
    return tuple(tuple(str(value) for value in row) for row in values)


def _quoted_title(title: str) -> str:
    """Quote a sheet title for A1 notation."""
    return f"'{title.replace(chr(39), chr(39) * 2)}'"


def _column_name(column: int) -> str:
    """Convert a zero-based column index to an A1 column name."""
    if column < 0:
        raise ValueError("Column index cannot be negative")
    name = ""
    value = column + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name
