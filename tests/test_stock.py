"""Tests for transactional stock operations."""

import csv
import sqlite3

import pytest

from ims.database.connection import connect
from ims.repositories.customers import CustomerRepository
from ims.repositories.movements import MovementRepository
from ims.repositories.products import ProductRepository
from ims.repositories.suppliers import SupplierRepository
from ims.services.settings import SettingsService
from ims.services.stock import StockError, StockService


def setup_product() -> tuple[sqlite3.Connection, int]:
    """Create an in-memory database containing one test product."""
    connection = connect(":memory:")
    product = ProductRepository(connection).create("SKU-1", "Widget")
    return connection, product.id


def test_receive_and_issue_update_stock_and_record_movements() -> None:
    """Receiving and issuing stock update quantity and movement history."""
    connection, product_id = setup_product()
    service = StockService(connection)

    assert service.receive(product_id, 10).quantity == 10
    assert service.issue(product_id, 4).quantity == 6
    movement_count = connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
    assert movement_count == 2


def test_receive_supports_large_integer_quantities() -> None:
    """Stock operations support quantities within the integer input range."""
    connection, product_id = setup_product()

    updated = StockService(connection).receive(product_id, 2_147_483_647)

    assert updated.quantity == 2_147_483_647


def test_issue_rejects_insufficient_stock_without_writing() -> None:
    """Issuing more than available stock leaves the database unchanged."""
    connection, product_id = setup_product()
    service = StockService(connection)

    with pytest.raises(StockError, match="Insufficient stock"):
        service.issue(product_id, 1)

    assert connection.execute("SELECT quantity FROM products").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 0


def test_negative_stock_setting_can_be_enabled_per_database() -> None:
    """The database can explicitly allow negative inventory for supported workflows."""
    connection, product_id = setup_product()
    settings = SettingsService(connection)
    service = StockService(connection, settings=settings)
    service.receive(product_id, 1)

    with pytest.raises(StockError, match="Insufficient stock"):
        service.issue(product_id, 2)

    settings.set("negative_stock_enabled", True)
    updated = service.issue(product_id, 2)

    assert updated.quantity == -1
    movement = connection.execute(
        "SELECT movement_type, quantity, previous_quantity, resulting_quantity "
        "FROM stock_movements WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (product_id,),
    ).fetchone()
    assert tuple(movement) == ("issue", -2, 1, -1)


def test_receive_rejects_zero_quantity() -> None:
    """Receiving zero units raises a stock validation error."""
    connection, product_id = setup_product()
    service = StockService(connection)

    with pytest.raises(StockError, match="greater than zero"):
        service.receive(product_id, 0)


def test_stock_operations_reject_decimal_quantities() -> None:
    """Stock quantities must be whole units rather than decimal values."""
    connection, product_id = setup_product()
    service = StockService(connection)

    with pytest.raises(StockError, match="must be an integer"):
        service.receive(product_id, 1.5)  # type: ignore[arg-type]
    with pytest.raises(StockError, match="must be an integer"):
        service.adjust(product_id, 1.5, "Correction")  # type: ignore[arg-type]


def test_stock_operation_rolls_back_when_movement_insert_fails() -> None:
    """A movement write failure rolls back the preceding quantity update."""
    connection, product_id = setup_product()
    connection.execute(
        "CREATE TRIGGER reject_movement BEFORE INSERT ON stock_movements "
        "BEGIN SELECT RAISE(ABORT, 'movement failure'); END;"
    )
    service = StockService(connection)

    with pytest.raises(sqlite3.IntegrityError, match="movement failure"):
        service.receive(product_id, 5)

    assert connection.execute("SELECT quantity FROM products").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 0


def test_adjust_sets_exact_quantity_and_records_reason() -> None:
    """Adjustment records the signed delta and old/new quantities."""
    connection, product_id = setup_product()
    service = StockService(connection)
    service.receive(product_id, 10)

    updated = service.adjust(product_id, 4, "Cycle count")
    movement = connection.execute(
        "SELECT movement_type, quantity, previous_quantity, resulting_quantity, reason "
        "FROM stock_movements WHERE movement_type = 'adjustment'"
    ).fetchone()

    assert updated.quantity == 4
    assert tuple(movement) == ("adjustment", -6, 10, 4, "Cycle count")


def test_adjust_requires_reason_and_nonnegative_quantity() -> None:
    """Invalid adjustments do not change stock or movement history."""
    connection, product_id = setup_product()
    service = StockService(connection)

    with pytest.raises(StockError, match="reason is required"):
        service.adjust(product_id, 2, " ")
    with pytest.raises(StockError, match="cannot be negative"):
        service.adjust(product_id, -1, "Correction")

    assert connection.execute("SELECT quantity FROM products").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 0


def test_movement_history_lists_product_audit_rows_and_filters() -> None:
    """Movement history exposes ordered product-level events and supports type filtering."""
    connection, product_id = setup_product()
    service = StockService(connection)
    service.receive(product_id, 10, "Restock")
    service.issue(product_id, 3, "Sales")
    service.adjust(product_id, 8, "Cycle count")

    history = MovementRepository(connection).list_history()
    assert [row.movement_type for row in history] == ["receive", "issue", "adjustment"]
    assert history[0].product_name == "Widget"
    assert history[0].quantity == 10
    assert history[0].resulting_quantity == 10

    filtered = MovementRepository(connection).list_history(movement_type="issue")
    assert len(filtered) == 1
    assert filtered[0].movement_type == "issue"
    assert filtered[0].quantity == -3


def test_movement_history_filters_by_supplier_and_customer() -> None:
    """Movement history can filter events by their linked business partner."""
    connection, product_id = setup_product()
    supplier = SupplierRepository(connection).create("Acme Supplies")
    customer = CustomerRepository(connection).create("Example Store")
    service = StockService(connection)
    service.receive(product_id, 10, supplier_id=supplier.id)
    service.issue(product_id, 2, customer_id=customer.id)

    supplier_rows = MovementRepository(connection).list_history(supplier_id=supplier.id)
    customer_rows = MovementRepository(connection).list_history(customer_id=customer.id)

    assert len(supplier_rows) == 1
    assert supplier_rows[0].supplier_name == "Acme Supplies"
    assert len(customer_rows) == 1
    assert customer_rows[0].customer_name == "Example Store"


def test_movement_history_exports_filtered_rows_to_csv(tmp_path) -> None:
    """Filtered movement history can be exported with stable audit columns."""
    connection, product_id = setup_product()
    service = StockService(connection)
    service.receive(product_id, 10, "Restock")
    service.issue(product_id, 3, "Sales")
    export_path = tmp_path / "movement-history.csv"

    MovementRepository(connection).export_csv(export_path, movement_type="issue")

    with export_path.open(newline="", encoding="utf-8") as export_file:
        rows = list(csv.DictReader(export_file))
    assert rows == [
        {
            "date": rows[0]["date"],
            "product": "SKU-1 - Widget",
            "type": "issue",
            "quantity": "-3",
            "previous_quantity": "10",
            "resulting_quantity": "7",
            "supplier": "",
            "customer": "",
            "reason": "Sales",
        }
    ]


def test_receive_and_issue_can_link_active_business_partners() -> None:
    """Receiving and issuing preserve their corresponding partner references."""
    connection, product_id = setup_product()
    supplier = SupplierRepository(connection).create("Acme Supplies")
    customer = CustomerRepository(connection).create("Example Store")
    service = StockService(connection)

    service.receive(product_id, 10, supplier_id=supplier.id)
    service.issue(product_id, 3, customer_id=customer.id)

    history = MovementRepository(connection).list_history()
    assert history[0].supplier_name == "Acme Supplies"
    assert history[0].customer_name is None
    assert history[1].supplier_name is None
    assert history[1].customer_name == "Example Store"


def test_partner_links_must_reference_active_partners() -> None:
    """Partner links reject archived records."""
    connection, product_id = setup_product()
    supplier = SupplierRepository(connection).create("Acme Supplies")
    SupplierRepository(connection).archive(supplier.id)
    service = StockService(connection)

    with pytest.raises(StockError, match="Supplier was not found"):
        service.receive(product_id, 1, supplier_id=supplier.id)
