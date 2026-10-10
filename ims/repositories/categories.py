"""Persistence operations for product categories."""

import sqlite3

from ims.models import Category


class CategoryRepository:
    """Store and retrieve active categories."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, name: str) -> Category:
        """Create an active category."""
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        cursor = self.connection.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        self.connection.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Category insert did not return an ID")
        return self.get(cursor.lastrowid)

    def get(self, category_id: int) -> Category:
        """Return an active category by ID."""
        row = self.connection.execute(
            "SELECT id, name FROM categories WHERE id = ? AND archived = 0", (category_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"Category {category_id} was not found")
        return Category(**dict(row))

    def list_active(self) -> list[Category]:
        """Return active categories sorted by name."""
        rows = self.connection.execute(
            "SELECT id, name FROM categories WHERE archived = 0 ORDER BY name"
        ).fetchall()
        return [Category(**dict(row)) for row in rows]

    def update(self, category_id: int, name: str) -> Category:
        """Rename an active category."""
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        cursor = self.connection.execute(
            "UPDATE categories SET name = ? WHERE id = ? AND archived = 0",
            (name, category_id),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"Category {category_id} was not found")
        return self.get(category_id)

    def archive(self, category_id: int) -> None:
        """Archive a category without deleting it."""
        self.connection.execute("UPDATE categories SET archived = 1 WHERE id = ?", (category_id,))
        self.connection.commit()
