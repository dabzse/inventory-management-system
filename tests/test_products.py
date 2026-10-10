"""Tests for product catalog filtering and repository lifecycle."""

import sqlite3

import pytest

from ims.database.connection import connect
from ims.repositories.categories import CategoryRepository
from ims.repositories.products import ProductRepository
from ims.services.stock import StockService


def test_product_search_filters_by_text_category_and_low_stock() -> None:
    """Catalog filters can be combined without exposing archived products."""
    connection = connect(":memory:")
    category = CategoryRepository(connection).create("Hardware")
    products = ProductRepository(connection)
    low = products.create("HW-1", "Small bolt", 5, category.id)
    high = products.create("HW-2", "Large bolt", 2, category.id)
    office = products.create("OFF-1", "Office chair", 0, None)
    StockService(connection).receive(high.id, 10)

    assert [product.id for product in products.search_active("bolt")] == [high.id, low.id]
    assert [product.id for product in products.search_active(category_id=category.id)] == [high.id, low.id]
    assert [product.id for product in products.search_active(low_stock=True)] == [office.id, low.id]
    assert [product.id for product in products.search_active("HW", category.id, True)] == [low.id]


def test_product_update_and_archive() -> None:
    """Products can be updated and then hidden instead of deleted."""
    connection = connect(":memory:")
    category = CategoryRepository(connection).create("Hardware")
    products = ProductRepository(connection)

    original = products.create("SKU-1", "Bolt", 2, category.id)
    updated = products.update(original.id, "SKU-2", "Hex bolt", 5, None)

    assert updated.sku == "SKU-2"
    assert updated.name == "Hex bolt"
    assert updated.reorder_level == 5
    assert updated.category_id is None

    products.archive(original.id)

    with pytest.raises(LookupError):
        products.get(original.id)
    assert products.search_active() == []


def test_product_search_supports_limit_and_offset() -> None:
    """Catalog queries can return a slice of active products for paging."""
    connection = connect(":memory:")
    products = ProductRepository(connection)
    products.create("A-1", "Alpha")
    products.create("A-2", "Beta")
    products.create("A-3", "Gamma")

    limited = products.search_active(limit=1)
    assert [item.sku for item in limited] == ["A-1"]

    paged = products.search_active(limit=1, offset=1)
    assert [item.sku for item in paged] == ["A-2"]


def test_product_repository_rejects_duplicate_skus() -> None:
    """The product SKU constraint rejects duplicate active records."""
    connection = connect(":memory:")
    products = ProductRepository(connection)
    products.create("SKU-1", "First product")

    with pytest.raises(sqlite3.IntegrityError):
        products.create("SKU-1", "Duplicate product")


def test_product_search_returns_an_empty_state() -> None:
    """Searching an empty catalog returns no products."""
    connection = connect(":memory:")

    assert ProductRepository(connection).search_active("missing") == []
