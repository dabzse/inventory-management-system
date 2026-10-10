"""Tests for category persistence and product associations."""

import sqlite3

import pytest

from ims.database.connection import connect
from ims.repositories.categories import CategoryRepository
from ims.repositories.products import ProductRepository


def test_products_keep_category_metadata() -> None:
    """A product can be created and retrieved with its category."""
    connection = connect(":memory:")
    categories = CategoryRepository(connection)
    category = categories.create("Hardware")

    product = ProductRepository(connection).create("SKU-1", "Widget", category_id=category.id)

    assert product.category_id == category.id
    assert product.category_name == "Hardware"


def test_categories_can_be_archived_without_deletion() -> None:
    """Archiving hides a category while preserving its database record."""
    connection = connect(":memory:")
    categories = CategoryRepository(connection)
    category = categories.create("Hardware")

    categories.archive(category.id)

    assert categories.list_active() == []
    assert connection.execute("SELECT archived FROM categories WHERE id = ?", (category.id,)).fetchone()[0] == 1


def test_category_names_are_required_and_unique() -> None:
    """The repository rejects blank and duplicate category names."""
    connection = connect(":memory:")
    categories = CategoryRepository(connection)

    with pytest.raises(ValueError, match="required"):
        categories.create(" ")
    categories.create("Hardware")
    with pytest.raises(sqlite3.IntegrityError):
        categories.create("Hardware")


def test_active_category_can_be_renamed() -> None:
    """Renaming preserves the category ID and updates its name."""
    connection = connect(":memory:")
    categories = CategoryRepository(connection)
    category = categories.create("Hardware")

    renamed = categories.update(category.id, "Tools")

    assert renamed.id == category.id
    assert renamed.name == "Tools"


def test_category_rename_rejects_duplicate_names() -> None:
    """Renaming cannot collide with another active category."""
    connection = connect(":memory:")
    categories = CategoryRepository(connection)
    first = categories.create("Hardware")
    second = categories.create("Office")

    with pytest.raises(sqlite3.IntegrityError):
        categories.update(second.id, first.name)
