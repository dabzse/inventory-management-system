"""Persistence operations for active products."""

import sqlite3

from ims.models import Product


class ProductRepository:
    """Store and retrieve product records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create a repository using the supplied SQLite connection."""
        self.connection = connection

    def create(
        self, sku: str, name: str, reorder_level: int = 0, category_id: int | None = None
    ) -> Product:
        """Create and return an active product."""
        cursor = self.connection.execute(
            "INSERT INTO products (sku, name, reorder_level, category_id) VALUES (?, ?, ?, ?)",
            (sku.strip(), name.strip(), reorder_level, category_id),
        )
        self.connection.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Product insert did not return an ID")
        return self.get(cursor.lastrowid)

    def get(self, product_id: int) -> Product:
        """Return an active product by ID or raise ``LookupError``."""
        row = self.connection.execute(
            "SELECT p.id, p.sku, p.name, p.quantity, p.reorder_level, "
            "p.category_id, c.name AS category_name FROM products p "
            "LEFT JOIN categories c ON c.id = p.category_id " \
            "WHERE p.id = ? " \
            "AND p.archived = 0",
            (product_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Product {product_id} was not found")
        return Product(**dict(row))

    def update(
        self,
        product_id: int,
        sku: str,
        name: str,
        reorder_level: int = 0,
        category_id: int | None = None,
    ) -> Product:
        """Update an active product's stored details."""
        sku = sku.strip()
        name = name.strip()
        if not sku:
            raise ValueError("Product SKU is required")
        if not name:
            raise ValueError("Product name is required")
        cursor = self.connection.execute(
            "UPDATE products SET sku = ?, name = ?, reorder_level = ?, category_id = ? "
            "WHERE id = ? AND archived = 0",
            (sku, name, reorder_level, category_id, product_id),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"Product {product_id} was not found")
        return self.get(product_id)

    def archive(self, product_id: int) -> None:
        """Archive a product without deleting it."""
        cursor = self.connection.execute(
            "UPDATE products SET archived = 1 WHERE id = ? AND archived = 0",
            (product_id,),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"Product {product_id} was not found")

    def list_active(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Product]:
        """Return active products sorted by name and SKU, optionally paginated."""
        return self.search_active(limit=limit, offset=offset)

    def search_active(
        self,
        search: str = "",
        category_id: int | None = None,
        low_stock: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Product]:
        """Return active products matching the requested catalog filters."""
        if limit is not None and limit < 0:
            raise ValueError("Limit must be zero or greater")
        if offset < 0:
            raise ValueError("Offset must be zero or greater")

        conditions = ["p.archived = 0"]
        parameters: list[object] = []
        search = search.strip()
        if search:
            conditions.append("(p.sku LIKE ? OR p.name LIKE ? OR c.name LIKE ?)")
            pattern = f"%{search}%"
            parameters.extend([pattern, pattern, pattern])
        if category_id is not None:
            conditions.append("p.category_id = ?")
            parameters.append(category_id)
        if low_stock:
            conditions.append("p.quantity <= p.reorder_level")

        query = (
            "SELECT p.id, p.sku, p.name, p.quantity, p.reorder_level, "
            "p.category_id, c.name AS category_name FROM products p "
            "LEFT JOIN categories c ON c.id = p.category_id "
            f"WHERE {' AND '.join(conditions)} ORDER BY p.name, p.sku"
        )
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            parameters.append(offset)

        rows = self.connection.execute(query, parameters).fetchall()
        return [Product(**dict(row)) for row in rows]
