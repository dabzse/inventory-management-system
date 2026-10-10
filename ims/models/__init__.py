"""Typed domain models for the inventory application."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """Represent an active product and its current stock quantity."""

    id: int
    sku: str
    name: str
    quantity: int
    reorder_level: int
    category_id: int | None = None
    category_name: str | None = None


@dataclass(frozen=True)
class Category:
    """Represent an active product category."""

    id: int
    name: str


@dataclass(frozen=True)
class Movement:
    """Represent an immutable stock movement record."""

    id: int
    product_id: int
    product_name: str
    sku: str
    movement_type: str
    quantity: int
    previous_quantity: int
    resulting_quantity: int
    reason: str | None = None
    created_at: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None


@dataclass(frozen=True)
class Supplier:
    """Represent an active supplier record."""

    id: int
    name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    transaction_count: int = 0


@dataclass(frozen=True)
class Customer:
    """Represent an active customer record."""

    id: int
    name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    transaction_count: int = 0
