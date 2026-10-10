"""Tests for tab-aware staged Google Sheets synchronization."""

from ims.services.google_sheets import (
    SheetTable,
    _column_name,
    _quoted_title,
    diff_tables,
    spreadsheet_id_from_url,
)


def test_diff_tables_tracks_changes_across_multiple_tabs() -> None:
    """Changes are isolated by tab and cell coordinate."""
    original = (
        SheetTable("Products", (("SKU", "Name"), ("A-1", "Widget"))),
        SheetTable("Suppliers", (("Name",), ("Acme",))),
    )
    current = (
        SheetTable("Products", (("SKU", "Name"), ("A-1", "Updated Widget"))),
        SheetTable("Suppliers", (("Name",), ("Acme Supplies",))),
        SheetTable("Notes", (("Text",), ("New tab",))),
    )

    changes = diff_tables(original, current)
    assert [(change.title, change.row, change.column, change.old_value, change.new_value) for change in changes] == [
        ("Products", 1, 1, "Widget", "Updated Widget"),
        ("Suppliers", 1, 0, "Acme", "Acme Supplies"),
        ("Notes", 0, 0, "", "Text"),
        ("Notes", 1, 0, "", "New tab"),
    ]


def test_a1_helpers_quote_tabs_and_convert_columns() -> None:
    """Sheet titles and large column indexes produce valid A1 components."""
    assert _quoted_title("Owner's Notes") == "'Owner''s Notes'"
    assert [_column_name(index) for index in (0, 25, 26, 51, 52)] == ["A", "Z", "AA", "AZ", "BA"]


def test_spreadsheet_id_accepts_url_or_raw_id() -> None:
    """The sync accepts the full URL users normally copy from a browser."""
    assert spreadsheet_id_from_url("spreadsheet-id") == "spreadsheet-id"
    assert (
        spreadsheet_id_from_url("https://docs.google.com/spreadsheets/d/spreadsheet-id/edit")
        == "spreadsheet-id"
    )
