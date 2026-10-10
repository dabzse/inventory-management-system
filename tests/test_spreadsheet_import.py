"""Tests for spreadsheet-to-inventory bootstrap imports."""

from ims.database.connection import connect
from ims.services.google_sheets import SheetTable
from ims.services.spreadsheet_import import SpreadsheetImportService


def test_import_preview_and_commit_maps_inventory_tabs() -> None:
    """Recognized tabs become inventory records in one committed import."""
    connection = connect(":memory:")
    service = SpreadsheetImportService(connection)
    tables = (
        SheetTable("Categories", (("Name",), ("Hardware",))),
        SheetTable(
            "Products",
            (
                ("SKU", "Product", "Quantity", "Reorder Level", "Category"),
                ("A-1", "Widget", "12", "3", "Hardware"),
            ),
        ),
        SheetTable("Extra", (("Value",), ("Ignored",))),
    )

    plan = service.preview(tables)
    assert plan.warnings == ("Skipped unrecognized tab: Extra",)
    service.commit(plan)

    product = connection.execute(
        "SELECT sku, name, quantity, reorder_level FROM products"
    ).fetchone()
    assert tuple(product) == ("A-1", "Widget", 12, 3)
    assert connection.execute("SELECT name FROM categories").fetchone()[0] == "Hardware"
