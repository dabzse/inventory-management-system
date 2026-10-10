"""Persistence operations for stock movement audit records."""

import csv
import sqlite3
from pathlib import Path

from ims.models import Movement


class MovementRepository:
    """Read stock movement history and filter it for product audit views."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create a movement repository using the supplied SQLite connection."""
        self.connection = connection

    def list_history(
        self,
        product_id: int | None = None,
        movement_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        supplier_id: int | None = None,
        customer_id: int | None = None,
    ) -> list[Movement]:
        """Return stock movement history entries in reverse-chronological order."""
        conditions = []
        parameters: list[object] = []
        if product_id is not None:
            conditions.append("m.product_id = ?")
            parameters.append(product_id)
        if movement_type:
            conditions.append("m.movement_type = ?")
            parameters.append(movement_type)
        if start_date:
            conditions.append("m.created_at >= ?")
            parameters.append(start_date)
        if end_date:
            conditions.append("m.created_at <= ?")
            parameters.append(end_date)
        if supplier_id is not None:
            conditions.append("m.supplier_id = ?")
            parameters.append(supplier_id)
        if customer_id is not None:
            conditions.append("m.customer_id = ?")
            parameters.append(customer_id)

        query = (
            "SELECT m.id, m.product_id, p.name AS product_name, p.sku, "
            "m.movement_type, m.quantity, m.previous_quantity, m.resulting_quantity, "
            "m.reason, m.created_at, m.supplier_id, s.name AS supplier_name, "
            "m.customer_id, c.name AS customer_name "
            "FROM stock_movements m "
            "JOIN products p ON p.id = m.product_id "
            "LEFT JOIN suppliers s ON s.id = m.supplier_id "
            "LEFT JOIN customers c ON c.id = m.customer_id "
        )
        if conditions:
            query += "WHERE " + " AND ".join(conditions) + " "
        query += "ORDER BY m.created_at ASC, m.id ASC"

        rows = self.connection.execute(query, parameters).fetchall()
        return [Movement(**dict(row)) for row in rows]

    def product_history(self, product_id: int) -> list[Movement]:
        """Return the movement audit log for one product."""
        return self.list_history(product_id=product_id)

    def export_csv(
        self,
        path: Path | str,
        product_id: int | None = None,
        movement_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        supplier_id: int | None = None,
        customer_id: int | None = None,
    ) -> Path:
        """Export filtered movement history to a UTF-8 CSV file."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = self.list_history(
            product_id=product_id,
            movement_type=movement_type,
            start_date=start_date,
            end_date=end_date,
            supplier_id=supplier_id,
            customer_id=customer_id,
        )
        with destination.open("w", newline="", encoding="utf-8") as export_file:
            writer = csv.writer(export_file)
            writer.writerow(
                [
                    "date",
                    "product",
                    "type",
                    "quantity",
                    "previous_quantity",
                    "resulting_quantity",
                    "supplier",
                    "customer",
                    "reason",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.created_at or "",
                        f"{row.sku} - {row.product_name}",
                        row.movement_type,
                        row.quantity,
                        row.previous_quantity,
                        row.resulting_quantity,
                        row.supplier_name or "",
                        row.customer_name or "",
                        row.reason or "",
                    ]
                )
        return destination
