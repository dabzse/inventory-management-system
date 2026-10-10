"""Persistence operations for supplier records."""

import sqlite3

from ims.models import Supplier


class SupplierRepository:
    """Store and retrieve active supplier records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Supplier:
        """Create an active supplier."""
        name = name.strip()
        if not name:
            raise ValueError("Supplier name is required")
        cursor = self.connection.execute(
            "INSERT INTO suppliers (name, email, phone, notes) VALUES (?, ?, ?, ?)",
            (name, email.strip() if email and email.strip() else None, phone.strip() if phone and phone.strip() else None, notes.strip() if notes and notes.strip() else None),
        )
        self.connection.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Supplier insert did not return an ID")
        return self.get(cursor.lastrowid)

    def get(self, supplier_id: int) -> Supplier:
        """Return an active supplier by ID."""
        row = self.connection.execute(
            "SELECT id, name, email, phone, notes, "
            "(SELECT COUNT(*) FROM stock_movements WHERE supplier_id = suppliers.id) "
            "AS transaction_count FROM suppliers WHERE id = ? AND archived = 0",
            (supplier_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Supplier {supplier_id} was not found")
        return Supplier(**dict(row))

    def list_active(self) -> list[Supplier]:
        """Return active suppliers sorted by name."""
        rows = self.connection.execute(
            "SELECT id, name, email, phone, notes, "
            "(SELECT COUNT(*) FROM stock_movements WHERE supplier_id = suppliers.id) "
            "AS transaction_count FROM suppliers WHERE archived = 0 ORDER BY name"
        ).fetchall()
        return [Supplier(**dict(row)) for row in rows]

    def update(
        self,
        supplier_id: int,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Supplier:
        """Rename and update supplier contact details."""
        name = name.strip()
        if not name:
            raise ValueError("Supplier name is required")
        cursor = self.connection.execute(
            "UPDATE suppliers SET name = ?, email = ?, phone = ?, notes = ? WHERE id = ? AND archived = 0",
            (
                name,
                email.strip() if email and email.strip() else None,
                phone.strip() if phone and phone.strip() else None,
                notes.strip() if notes and notes.strip() else None,
                supplier_id,
            ),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"Supplier {supplier_id} was not found")
        return self.get(supplier_id)

    def archive(self, supplier_id: int) -> None:
        """Archive a supplier without deleting it."""
        self.connection.execute("UPDATE suppliers SET archived = 1 WHERE id = ?", (supplier_id,))
        self.connection.commit()
