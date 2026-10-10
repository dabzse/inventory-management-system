"""Focused tests for critical stock-operation dialog behavior."""

import importlib
import os

import pytest

from ims.database.connection import connect
from ims.repositories.products import ProductRepository
from ims.services.access import UserSession
from ims.services.stock import StockService
from ims.ui.dialogs import CustomerDialog, StockDialog, SupplierDialog
from ims.ui.main_window import MainWindow

QtWidgets = importlib.import_module("PySide6.QtWidgets")


@pytest.fixture(scope="session", name="qt_application")
def create_qt_application() -> object:
    """Create one offscreen Qt application for the UI tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_receive_stock_dialog_submits_operation(qt_application: object) -> None:
    """The receive form saves the selected quantity and closes successfully."""
    assert qt_application is not None
    connection = connect(":memory:")
    products = ProductRepository(connection)
    product = products.create("SKU-UI", "UI Widget")
    dialog = StockDialog(products, StockService(connection), "receive")

    dialog.quantity_input.setValue(3)
    dialog.reason_input.setText("UI test receipt")
    dialog.save_button.click()

    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert products.get(product.id).quantity == 3
    movement = connection.execute(
        "SELECT reason FROM stock_movements WHERE product_id = ?", (product.id,)
    ).fetchone()
    assert movement["reason"] == "UI test receipt"
    dialog.deleteLater()
    connection.close()


def test_receive_to_issue_workflow_updates_stock(qt_application: object) -> None:
    """The receive and issue dialogs complete one stock workflow in sequence."""
    assert qt_application is not None
    connection = connect(":memory:")
    products = ProductRepository(connection)
    product = products.create("SKU-FLOW", "Workflow Widget")
    stock = StockService(connection)

    receive_dialog = StockDialog(products, stock, "receive")
    receive_dialog.quantity_input.setValue(10)
    receive_dialog.reason_input.setText("Workflow receipt")
    receive_dialog.save_button.click()

    issue_dialog = StockDialog(products, stock, "issue")
    issue_dialog.quantity_input.setValue(4)
    issue_dialog.reason_input.setText("Workflow issue")
    issue_dialog.save_button.click()

    assert issue_dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert products.get(product.id).quantity == 6
    movements = connection.execute(
        "SELECT movement_type, quantity FROM stock_movements "
        "WHERE product_id = ? ORDER BY id",
        (product.id,),
    ).fetchall()
    assert [tuple(movement) for movement in movements] == [("receive", 10), ("issue", -4)]
    receive_dialog.deleteLater()
    issue_dialog.deleteLater()
    connection.close()


def test_main_navigation_highlights_selected_section(qt_application: object) -> None:
    """Navigation buttons behave like exclusive selected tabs."""
    assert qt_application is not None
    connection = connect(":memory:")
    products = ProductRepository(connection)
    window = MainWindow(
        products,
        StockService(connection),
        UserSession(1, "tester", ("Administrator",)),
    )

    assert window.dashboard_button.isChecked()
    window.products_button.click()
    assert window.products_button.isChecked()
    assert not window.dashboard_button.isChecked()
    window.reports_button.click()
    assert window.reports_button.isChecked()
    assert not window.products_button.isChecked()
    window.deleteLater()
    connection.close()


def test_navigation_buttons_without_options_clear_secondary_row(
    qt_application: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting options with no secondary actions clears the second row while keeping it visible."""
    assert qt_application is not None
    connection = connect(":memory:")
    products = ProductRepository(connection)
    window = MainWindow(
        products,
        StockService(connection),
        UserSession(1, "tester", ("Administrator",)),
    )
    window.show()

    # Initial state (Dashboard) has no secondary buttons, but the secondary row is visible
    assert window.secondary_layout.count() == 0
    assert window.secondary_row.isVisible()
    initial_y = window.table.y()

    # Switching to Products displays secondary controls and keeps secondary row visible
    window.products_button.click()
    assert window.secondary_layout.count() > 0
    assert window.secondary_row.isVisible()
    assert window.table.y() == initial_y

    # Switching to Suppliers clears the second row while keeping it visible
    monkeypatch.setattr(SupplierDialog, "exec", lambda _self: 0)
    window.suppliers_button.click()
    assert window.secondary_layout.count() == 0
    assert window.secondary_row.isVisible()
    assert window.suppliers_button.isChecked()
    assert window.table.y() == initial_y

    # Switching to Stock operations displays secondary controls
    window.stock_operations_button.click()
    assert window.secondary_layout.count() > 0
    assert window.secondary_row.isVisible()

    # Switching to Customers clears the second row while keeping it visible
    monkeypatch.setattr(CustomerDialog, "exec", lambda _self: 0)
    window.customers_button.click()
    assert window.secondary_layout.count() == 0
    assert window.secondary_row.isVisible()
    assert window.customers_button.isChecked()
    assert window.table.y() == initial_y

    # Secondary manage buttons for suppliers/customers no longer exist
    assert not hasattr(window, "manage_suppliers_button")
    assert not hasattr(window, "manage_customers_button")

    window.deleteLater()
    connection.close()


def test_suppliers_and_customers_permissions_by_role(qt_application: object) -> None:
    """Primary supplier and customer buttons respect write permissions."""
    assert qt_application is not None
    connection = connect(":memory:")
    products = ProductRepository(connection)

    admin_window = MainWindow(
        products,
        StockService(connection),
        UserSession(1, "admin", ("Administrator",)),
    )
    assert admin_window.suppliers_button.isEnabled()
    assert admin_window.customers_button.isEnabled()
    admin_window.deleteLater()

    viewer_window = MainWindow(
        products,
        StockService(connection),
        UserSession(2, "viewer", ("Viewer",)),
    )
    assert not viewer_window.suppliers_button.isEnabled()
    assert not viewer_window.customers_button.isEnabled()
    viewer_window.deleteLater()

    connection.close()

