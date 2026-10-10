"""Persistence operations for customer records."""

import sqlite3

from ims.models import Customer


class CustomerRepository:
    """Store and retrieve active customer records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Customer:
        """Create an active customer."""
        name = name.strip()
        if not name:
            raise ValueError("Customer name is required")
        cursor = self.connection.execute(
            "INSERT INTO customers (name, email, phone, notes) VALUES (?, ?, ?, ?)",
            (name, email.strip() if email and email.strip() else None, phone.strip() if phone and phone.strip() else None, notes.strip() if notes and notes.strip() else None),
        )
        self.connection.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Customer insert did not return an ID")
        return self.get(cursor.lastrowid)

    def get(self, customer_id: int) -> Customer:
        """Return an active customer by ID."""
        row = self.connection.execute(
            "SELECT id, name, email, phone, notes, "
            "(SELECT COUNT(*) FROM stock_movements WHERE customer_id = customers.id) "
            "AS transaction_count FROM customers WHERE id = ? AND archived = 0",
            (customer_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Customer {customer_id} was not found")
        return Customer(**dict(row))

    def list_active(self) -> list[Customer]:
        """Return active customers sorted by name."""
        rows = self.connection.execute(
            "SELECT id, name, email, phone, notes, "
            "(SELECT COUNT(*) FROM stock_movements WHERE customer_id = customers.id) "
            "AS transaction_count FROM customers WHERE archived = 0 ORDER BY name"
        ).fetchall()
        return [Customer(**dict(row)) for row in rows]

    def update(
        self,
        customer_id: int,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Customer:
        """Rename and update customer contact details."""
        name = name.strip()
        if not name:
            raise ValueError("Customer name is required")
        cursor = self.connection.execute(
            "UPDATE customers SET name = ?, email = ?, phone = ?, notes = ? WHERE id = ? AND archived = 0",
            (
                name,
                email.strip() if email and email.strip() else None,
                phone.strip() if phone and phone.strip() else None,
                notes.strip() if notes and notes.strip() else None,
                customer_id,
            ),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"Customer {customer_id} was not found")
        return self.get(customer_id)

    def archive(self, customer_id: int) -> None:
        """Archive a customer without deleting it."""
        self.connection.execute("UPDATE customers SET archived = 1 WHERE id = ?", (customer_id,))
        self.connection.commit()
