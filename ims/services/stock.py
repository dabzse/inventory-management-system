"""Transactional stock receiving and issuing rules."""

import sqlite3

from ims.database.connection import transaction
from ims.models import Product
from ims.services.settings import SettingsService


class StockError(ValueError):
    """Raised when a stock operation violates an inventory rule."""


class StockService:
    """Apply validated stock changes and record immutable movements."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        settings: SettingsService | None = None,
    ) -> None:
        """Create a stock service using the supplied SQLite connection."""
        self.connection = connection
        self.settings = settings or SettingsService(connection)

    def receive(
        self,
        product_id: int,
        quantity: int,
        reason: str = "",
        supplier_id: int | None = None,
    ) -> Product:
        """Increase stock for a product and return its updated record."""
        self._validate_integer_quantity(quantity)
        return self._change(product_id, quantity, "receive", reason, supplier_id=supplier_id)

    def issue(
        self,
        product_id: int,
        quantity: int,
        reason: str = "",
        customer_id: int | None = None,
    ) -> Product:
        """Decrease stock for a product and return its updated record."""
        self._validate_integer_quantity(quantity)
        if quantity <= 0:
            raise StockError("Issue quantity must be greater than zero")
        return self._change(product_id, -quantity, "issue", reason, customer_id=customer_id)

    def adjust(self, product_id: int, new_quantity: int, reason: str) -> Product:
        """Set stock to an exact quantity and require an audit reason."""
        self._validate_integer_quantity(new_quantity)
        if new_quantity < 0:
            raise StockError("Adjusted quantity cannot be negative")
        if not reason.strip():
            raise StockError("Adjustment reason is required")
        with transaction(self.connection):
            row = self.connection.execute(
                "SELECT quantity FROM products WHERE id = ? AND archived = 0", (product_id,)
            ).fetchone()
            if row is None:
                raise StockError("Product was not found")
            previous = row["quantity"]
            if new_quantity < 0 and not self.settings.is_negative_stock_enabled():
                raise StockError("Adjusted quantity cannot be negative")
            self.connection.execute(
                "UPDATE products SET quantity = ? WHERE id = ?", (new_quantity, product_id)
            )
            self.connection.execute(
                "INSERT INTO stock_movements "
                "(product_id, movement_type, quantity, previous_quantity, resulting_quantity, reason) "
                "VALUES (?, 'adjustment', ?, ?, ?, ?)",
                (product_id, new_quantity - previous, previous, new_quantity, reason.strip()),
            )
            updated = self.connection.execute(
                "SELECT id, sku, name, quantity, reorder_level FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        return Product(**dict(updated))

    def _change(
        self,
        product_id: int,
        delta: int,
        movement_type: str,
        reason: str,
        supplier_id: int | None = None,
        customer_id: int | None = None,
    ) -> Product:
        """Apply one signed stock change inside an atomic transaction."""
        if delta == 0:
            raise StockError("Quantity must be greater than zero")
        if supplier_id is not None and movement_type != "receive":
            raise StockError("Suppliers can only be linked to received stock")
        if customer_id is not None and movement_type != "issue":
            raise StockError("Customers can only be linked to issued stock")
        with transaction(self.connection):
            self._validate_partner(supplier_id, "suppliers", "Supplier")
            self._validate_partner(customer_id, "customers", "Customer")
            row = self.connection.execute(
                "SELECT quantity FROM products WHERE id = ? AND archived = 0", (product_id,)
            ).fetchone()
            if row is None:
                raise StockError("Product was not found")
            previous = row["quantity"]
            resulting = previous + delta
            if resulting < 0 and not self.settings.is_negative_stock_enabled():
                raise StockError("Insufficient stock")
            self.connection.execute(
                "UPDATE products SET quantity = ? WHERE id = ?", (resulting, product_id)
            )
            self.connection.execute(
                "INSERT INTO stock_movements "
                "(" \
                    "product_id, movement_type, quantity, " \
                    "previous_quantity, resulting_quantity, reason, supplier_id, customer_id" \
                ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    product_id,
                    movement_type,
                    delta,
                    previous,
                    resulting,
                    reason.strip() or None,
                    supplier_id,
                    customer_id,
                ),
            )
            updated = self.connection.execute(
                "SELECT id, sku, name, quantity, reorder_level FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        return Product(**dict(updated))

    def _validate_partner(self, partner_id: int | None, table: str, label: str) -> None:
        """Ensure an optional partner reference points to an active record."""
        if partner_id is None:
            return
        row = self.connection.execute(
            f"SELECT id FROM {table} WHERE id = ? AND archived = 0", (partner_id,)
        ).fetchone()
        if row is None:
            raise StockError(f"{label} was not found")

    @staticmethod
    def _validate_integer_quantity(quantity: int) -> None:
        """Reject values that cannot be represented as whole stock units."""
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise StockError("Quantity must be an integer")
