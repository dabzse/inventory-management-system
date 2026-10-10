"""Preview and commit inventory data imported from spreadsheet tabs."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from ims.database.connection import transaction
from ims.services.google_sheets import SheetTable


@dataclass(frozen=True)
class ImportPlan:
    """Validated spreadsheet rows ready for an explicit database commit."""

    categories: tuple[str, ...]
    suppliers: tuple[dict[str, str], ...]
    customers: tuple[dict[str, str], ...]
    products: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


class SpreadsheetImportError(ValueError):
    """Raised when spreadsheet inventory data cannot be imported safely."""


class SpreadsheetImportService:
    """Map recognized tabs to inventory entities and commit them atomically."""

    TAB_ALIASES: ClassVar[dict[str, str]] = {
        "category": "categories",
        "categories": "categories",
        "supplier": "suppliers",
        "suppliers": "suppliers",
        "customer": "customers",
        "customers": "customers",
        "product": "products",
        "products": "products",
    }

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create an importer using an initialized inventory database."""
        self.connection = connection

    def preview(self, tables: Iterable[SheetTable]) -> ImportPlan:
        """Parse recognized tabs without changing the database."""
        categories: list[str] = []
        suppliers: list[dict[str, str]] = []
        customers: list[dict[str, str]] = []
        products: list[dict[str, str]] = []
        warnings: list[str] = []
        for table in tables:
            entity = self.TAB_ALIASES.get(_normalize_name(table.title))
            if entity is None:
                warnings.append(f"Skipped unrecognized tab: {table.title}")
                continue
            rows = _rows_as_dicts(table)
            try:
                if entity == "categories":
                    categories.extend(_category_rows(rows))
                elif entity == "suppliers":
                    suppliers.extend(_partner_rows(rows))
                elif entity == "customers":
                    customers.extend(_partner_rows(rows))
                else:
                    products.extend(_product_rows(rows))
            except (KeyError, ValueError) as error:
                raise SpreadsheetImportError(f"Could not parse tab '{table.title}': {error}") from error
        return ImportPlan(
            tuple(name for name in dict.fromkeys(categories) if name),
            tuple(suppliers),
            tuple(customers),
            tuple(products),
            tuple(warnings),
        )

    def commit(self, plan: ImportPlan) -> None:
        """Commit the import plan as one transaction."""
        with transaction(self.connection):
            category_ids: dict[str, int] = {}
            for name in plan.categories:
                self.connection.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
                row = self.connection.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
                category_ids[name] = row[0]
            for table, rows in (("suppliers", plan.suppliers), ("customers", plan.customers)):
                for row in rows:
                    if not row["name"]:
                        raise SpreadsheetImportError(f"{table.title()} require a name")
                    self.connection.execute(
                        f"INSERT INTO {table} (name, email, phone, notes) VALUES (?, ?, ?, ?)",
                        (row["name"], row["email"], row["phone"], row["notes"]),
                    )
            for product in plan.products:
                if not product["sku"] or not product["name"]:
                    raise SpreadsheetImportError("Products require SKU and name")
                category_id = category_ids.get(product["category"])
                self.connection.execute(
                    "INSERT INTO products (sku, name, quantity, reorder_level, category_id) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(sku) DO UPDATE SET name = excluded.name, "
                    "quantity = excluded.quantity, reorder_level = excluded.reorder_level, "
                    "category_id = excluded.category_id",
                    (
                        product["sku"],
                        product["name"],
                        int(product["quantity"] or 0),
                        int(product["reorder_level"] or 0),
                        category_id,
                    ),
                )


def _rows_as_dicts(table: SheetTable) -> list[dict[str, str]]:
    """Convert the first row of a tab into normalized header mappings."""
    if not table.values:
        return []
    headers = [_normalize_name(value) for value in table.values[0]]
    return [
        {header: values[index] if index < len(values) else "" for index, header in enumerate(headers)}
        for values in table.values[1:]
    ]


def _category_rows(rows: list[dict[str, str]]) -> list[str]:
    """Extract category names from flexible category headers."""
    return [row.get("name", row.get("category", "")).strip() for row in rows]


def _partner_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Extract common partner fields from a tab."""
    return [
        {
            "name": row.get("name", "").strip(),
            "email": row.get("email", "").strip(),
            "phone": row.get("phone", "").strip(),
            "notes": row.get("notes", "").strip(),
        }
        for row in rows
    ]


def _product_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Extract product fields and validate numeric values."""
    products = []
    for row in rows:
        quantity = row.get("quantity", "").strip()
        reorder_level = row.get("reorderlevel", row.get("reorder", "")).strip()
        int(quantity or 0)
        int(reorder_level or 0)
        products.append(
            {
                "sku": row.get("sku", "").strip(),
                "name": row.get("name", row.get("product", "")).strip(),
                "quantity": quantity,
                "reorder_level": reorder_level,
                "category": row.get("category", "").strip(),
            }
        )
    return products


def _normalize_name(value: str) -> str:
    """Normalize tab and column labels for matching."""
    return "".join(character for character in value.lower().strip() if character.isalnum())
