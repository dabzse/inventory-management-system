"""Tests for supplier and customer partner repositories."""

import pytest

from ims.database.connection import connect
from ims.repositories.customers import CustomerRepository
from ims.repositories.products import ProductRepository
from ims.repositories.suppliers import SupplierRepository
from ims.services.stock import StockService


def test_supplier_repository_lifecycle() -> None:
    """Supplier records can be created, edited, and archived."""
    connection = connect(":memory:")
    repo = SupplierRepository(connection)

    created = repo.create("Acme Parts", "ops@acme.test", "555-0101")
    assert created.name == "Acme Parts"

    updated = repo.update(created.id, "Acme Parts Ltd", "sales@acme.test", "555-0102")
    assert updated.name == "Acme Parts Ltd"
    assert updated.phone == "555-0102"

    repo.archive(created.id)
    assert repo.list_active() == []
    with pytest.raises(LookupError):
        repo.get(created.id)


def test_customer_repository_lifecycle() -> None:
    """Customer records can be created, edited, and archived."""
    connection = connect(":memory:")
    repo = CustomerRepository(connection)

    created = repo.create("Northwind Retail", "hello@northwind.test", "555-2100")
    assert created.email == "hello@northwind.test"

    updated = repo.update(created.id, "Northwind Retail Group", None, "555-2109")
    assert updated.name == "Northwind Retail Group"
    assert updated.email is None

    repo.archive(created.id)
    assert repo.list_active() == []
    with pytest.raises(LookupError):
        repo.get(created.id)


def test_partner_notes_and_transaction_counts_persist_to_disk(tmp_path) -> None:
    """Partner notes and linked movement counts survive an on-disk repository read."""
    connection = connect(tmp_path / "partners.sqlite3")
    products = ProductRepository(connection)
    supplier = SupplierRepository(connection).create("Acme Parts", notes="Preferred supplier")
    customer = CustomerRepository(connection).create("Northwind Retail", notes="Local store")
    product = products.create("SKU-1", "Widget")
    stock = StockService(connection)

    stock.receive(product.id, 10, supplier_id=supplier.id)
    stock.issue(product.id, 2, customer_id=customer.id)

    assert SupplierRepository(connection).get(supplier.id).notes == "Preferred supplier"
    assert SupplierRepository(connection).get(supplier.id).transaction_count == 1
    assert CustomerRepository(connection).get(customer.id).notes == "Local store"
    assert CustomerRepository(connection).get(customer.id).transaction_count == 1
    connection.close()
