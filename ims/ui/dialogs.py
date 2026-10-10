"""Dialogs for creating products and changing stock."""

import importlib
import sqlite3
from pathlib import Path
from typing import Any

from ims.config import google_sheets_settings
from ims.models import Product
from ims.repositories.categories import CategoryRepository
from ims.repositories.customers import CustomerRepository
from ims.repositories.movements import MovementRepository
from ims.repositories.products import ProductRepository
from ims.repositories.suppliers import SupplierRepository
from ims.services.access import UserSession, authenticate, create_user, list_groups
from ims.services.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsError,
    SheetTable,
    diff_tables,
    spreadsheet_id_from_url,
)
from ims.services.schema import ColumnDefinition, create_custom_table
from ims.services.spreadsheet_import import SpreadsheetImportError, SpreadsheetImportService
from ims.services.stock import StockError, StockService
from ims.ui.export_worker import CsvExportWorker

QtWidgets = importlib.import_module("PySide6.QtWidgets")
QtCore = importlib.import_module("PySide6.QtCore")

EDIT_SELECTED_TEXT = "Edit selected"
ADD_CATEGORY_TEXT = "Add category"
ARCHIVE_SELECTED_TEXT = "Archive selected"
CLOSE_TEXT = "Close"
ADD_SUPPLIER_TEXT = "Add supplier"
ADD_CUSTOMER_TEXT = "Add customer"
NO_CATEGORY_TEXT = "No category"
NO_CONTACT_TEXT = "No contact"
ALL_PRODUCTS_TEXT = "All products"
ALL_TYPES_TEXT = "All types"
ALL_SUPPLIERS_TEXT = "All suppliers"
ALL_CUSTOMERS_TEXT = "All customers"
REFRESH_TEXT = "Refresh"
EXPORT_CSV_TEXT = "Export CSV"
ADD_COLUMN_TEXT = "Add column"
REMOVE_COLUMN_TEXT = "Remove column"
LOAD_SHEETS_TEXT = "Load spreadsheet"
COMMIT_SHEETS_TEXT = "Commit changes"


class ProductDialog(QtWidgets.QDialog):
    """Collect the fields required to create a product."""

    def __init__(
        self,
        products: ProductRepository,
        categories: CategoryRepository,
        parent: object = None,
    ) -> None:
        """Create a product form backed by the given repository."""
        super().__init__(parent)
        self.products = products
        self.categories = categories
        self.created_product: Product | None = None
        self.setWindowTitle("Add product")
        self.resize(500, 300)
        self._build_form()

    def _build_form(self) -> None:
        """Build the product fields and dialog buttons."""
        layout = QtWidgets.QFormLayout(self)
        self.sku_input = QtWidgets.QLineEdit(self)
        self.name_input = QtWidgets.QLineEdit(self)
        self.reorder_input = QtWidgets.QSpinBox(self)
        self.reorder_input.setRange(0, 2_147_483_647)
        self.category_input = QtWidgets.QComboBox(self)
        self.category_input.addItem(NO_CATEGORY_TEXT, None)
        for category in self.categories.list_active():
            self.category_input.addItem(category.name, category.id)
        layout.addRow("SKU", self.sku_input)
        layout.addRow("Name", self.name_input)
        layout.addRow("Reorder level", self.reorder_input)
        layout.addRow("Category", self.category_input)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        self.save_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        """Validate and persist the product form."""
        sku = self.sku_input.text().strip()
        name = self.name_input.text().strip()
        if not sku or not name:
            QtWidgets.QMessageBox.warning(self, "Invalid product", "SKU and name are required.")
            return
        try:
            self.created_product = self.products.create(
                sku, name, self.reorder_input.value(), self.category_input.currentData()
            )
        except sqlite3.IntegrityError as error:
            QtWidgets.QMessageBox.critical(self, "Could not save product", str(error))
            return
        self.accept()


class CategoryDialog(QtWidgets.QDialog):
    """Create or archive product categories."""

    def __init__(self, categories: CategoryRepository, parent: object = None) -> None:
        super().__init__(parent)
        self.categories = categories
        self.setWindowTitle("Manage categories")
        self.resize(500, 300)
        layout = QtWidgets.QVBoxLayout(self)
        self.name_input = QtWidgets.QLineEdit(self)
        self.name_input.setPlaceholderText("New category name")
        add_button = QtWidgets.QPushButton(ADD_CATEGORY_TEXT, self)
        add_button.clicked.connect(self._add)
        edit_button = QtWidgets.QPushButton(EDIT_SELECTED_TEXT, self)
        edit_button.clicked.connect(self._edit)
        layout.addWidget(self.name_input)
        layout.addWidget(add_button)
        layout.addWidget(edit_button)
        self.category_list = QtWidgets.QListWidget(self)
        layout.addWidget(self.category_list)
        archive_button = QtWidgets.QPushButton(ARCHIVE_SELECTED_TEXT, self)
        archive_button.clicked.connect(self._archive)
        layout.addWidget(archive_button)
        close_button = QtWidgets.QPushButton(CLOSE_TEXT, self)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        self._refresh()

    def _refresh(self) -> None:
        self.category_list.clear()
        for category in self.categories.list_active():
            item = QtWidgets.QListWidgetItem(category.name, self.category_list)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, category.id)

    def _add(self) -> None:
        try:
            self.categories.create(self.name_input.text())
        except (ValueError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not add category", str(error))
            return
        self.name_input.clear()
        self._refresh()

    def _archive(self) -> None:
        item = self.category_list.currentItem()
        if item is not None:
            self.categories.archive(item.data(QtCore.Qt.ItemDataRole.UserRole))
            self._refresh()

    def _edit(self) -> None:
        """Rename the selected category using the name field."""
        item = self.category_list.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(self, "No category selected", "Select a category first.")
            return
        try:
            self.categories.update(item.data(QtCore.Qt.ItemDataRole.UserRole), self.name_input.text())
        except (ValueError, LookupError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not edit category", str(error))
            return
        self.name_input.clear()
        self._refresh()


class StockDialog(QtWidgets.QDialog):
    """Collect and apply a receive, issue, or adjustment operation."""

    def __init__(
        self,
        products: ProductRepository,
        stock: StockService,
        operation: str,
        parent: object = None,
        suppliers: SupplierRepository | None = None,
        customers: CustomerRepository | None = None,
    ) -> None:
        """Create a stock operation form for receiving or issuing units."""
        super().__init__(parent)
        self.products = products
        self.stock = stock
        self.operation = operation
        self.suppliers = suppliers
        self.customers = customers
        titles = {"receive": "Receive stock", "issue": "Issue stock", "adjust": "Adjust stock"}
        self.resize(500, 300)
        self.setWindowTitle(titles[operation])
        self._build_form()

    def _build_form(self) -> None:
        """Build the product, quantity, and reason fields."""
        layout = QtWidgets.QFormLayout(self)
        self.product_input = QtWidgets.QComboBox(self)
        self.product_ids: list[int] = []
        self.product_quantities: list[int] = []
        for product in self.products.list_active():
            self.product_ids.append(product.id)
            self.product_quantities.append(product.quantity)
            self.product_input.addItem(f"{product.sku} - {product.name}")
        self.quantity_input = QtWidgets.QSpinBox(self)
        self.quantity_input.setRange(0 if self.operation == "adjust" else 1, 2_147_483_647)
        self.reason_input = QtWidgets.QLineEdit(self)
        self.preview = QtWidgets.QLabel(self)
        self.partner_input = QtWidgets.QComboBox(self)
        partner_label = self._configure_partner_input()
        if self.operation == "adjust" and self.product_quantities:
            self.quantity_input.setValue(self.product_quantities[0])
        layout.addRow("Product", self.product_input)
        layout.addRow("New quantity" if self.operation == "adjust" else "Quantity", self.quantity_input)
        layout.addRow("Reason", self.reason_input)
        if partner_label is not None:
            layout.addRow(partner_label, self.partner_input)
        if self.operation == "adjust":
            layout.addRow("Result", self.preview)
            self.product_input.currentIndexChanged.connect(self._update_preview)
            self.quantity_input.valueChanged.connect(self._update_preview)
            self._update_preview()
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        self.save_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _configure_partner_input(self) -> str | None:
        """Configure the supplier or customer selector for this operation."""
        partner_config = {
            "receive": ("Supplier", "No supplier", self.suppliers),
            "issue": ("Customer", "No customer", self.customers),
        }.get(self.operation)
        if partner_config is None:
            return None
        label, empty_label, repository = partner_config
        self.partner_input.addItem(empty_label, None)
        if repository is not None:
            for partner in repository.list_active():
                self.partner_input.addItem(partner.name, partner.id)
        return label

    def _save(self) -> None:
        """Validate and apply the selected stock operation."""
        self.save_button.setEnabled(False)
        if not self.product_ids:
            QtWidgets.QMessageBox.warning(self, "No products", "Create a product first.")
            self.save_button.setEnabled(True)
            return
        product_id = self.product_ids[self.product_input.currentIndex()]
        quantity = self.quantity_input.value()
        reason = self.reason_input.text().strip()
        try:
            if self.operation == "receive":
                self.stock.receive(
                    product_id,
                    quantity,
                    reason,
                    supplier_id=self.partner_input.currentData(),
                )
            elif self.operation == "issue":
                self.stock.issue(
                    product_id,
                    quantity,
                    reason,
                    customer_id=self.partner_input.currentData(),
                )
            else:
                self.stock.adjust(product_id, quantity, reason)
        except StockError as error:
            QtWidgets.QMessageBox.warning(self, "Stock operation failed", str(error))
            self.save_button.setEnabled(True)
            return
        self.accept()

    def _update_preview(self) -> None:
        """Show the quantity that the adjustment will produce."""
        if self.product_ids:
            current = self.product_quantities[self.product_input.currentIndex()]
            self.preview.setText(f"{current} -> {self.quantity_input.value()}")


class SupplierDialog(QtWidgets.QDialog):
    """Create, edit, and archive suppliers."""

    def __init__(self, suppliers: SupplierRepository, parent: object = None) -> None:
        super().__init__(parent)
        self.suppliers = suppliers
        self.setWindowTitle("Manage suppliers")
        self.resize(520, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self.name_input = QtWidgets.QLineEdit(self)
        self.email_input = QtWidgets.QLineEdit(self)
        self.phone_input = QtWidgets.QLineEdit(self)
        self.notes_input = QtWidgets.QLineEdit(self)
        layout.addWidget(QtWidgets.QLabel("Name", self))
        layout.addWidget(self.name_input)
        layout.addWidget(QtWidgets.QLabel("Email", self))
        layout.addWidget(self.email_input)
        layout.addWidget(QtWidgets.QLabel("Phone", self))
        layout.addWidget(self.phone_input)
        layout.addWidget(QtWidgets.QLabel("Notes", self))
        layout.addWidget(self.notes_input)
        add_button = QtWidgets.QPushButton("Add supplier", self)
        add_button.clicked.connect(self._add)
        edit_button = QtWidgets.QPushButton(EDIT_SELECTED_TEXT, self)
        edit_button.clicked.connect(self._edit)
        layout.addWidget(add_button)
        layout.addWidget(edit_button)
        self.supplier_list = QtWidgets.QListWidget(self)
        layout.addWidget(self.supplier_list)
        archive_button = QtWidgets.QPushButton(ARCHIVE_SELECTED_TEXT, self)
        archive_button.clicked.connect(self._archive)
        layout.addWidget(archive_button)
        close_button = QtWidgets.QPushButton(CLOSE_TEXT, self)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        self._refresh()

    def _refresh(self) -> None:
        self.supplier_list.clear()
        for supplier in self.suppliers.list_active():
            item = QtWidgets.QListWidgetItem(
                f"{supplier.name} ({supplier.email or supplier.phone or NO_CONTACT_TEXT}) "
                f"- {supplier.transaction_count} transactions",
                self.supplier_list,
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, supplier.id)

    def _add(self) -> None:
        try:
            self.suppliers.create(
                self.name_input.text(),
                self.email_input.text(),
                self.phone_input.text(),
                self.notes_input.text(),
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not add supplier", str(error))
            return
        self.name_input.clear()
        self.email_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        self._refresh()

    def _edit(self) -> None:
        item = self.supplier_list.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(self, "No supplier selected", "Select a supplier first.")
            return
        try:
            self.suppliers.update(
                item.data(QtCore.Qt.ItemDataRole.UserRole),
                self.name_input.text(),
                self.email_input.text(),
                self.phone_input.text(),
                self.notes_input.text(),
            )
        except (ValueError, LookupError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not edit supplier", str(error))
            return
        self.name_input.clear()
        self.email_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        self._refresh()

    def _archive(self) -> None:
        item = self.supplier_list.currentItem()
        if item is not None:
            self.suppliers.archive(item.data(QtCore.Qt.ItemDataRole.UserRole))
            self._refresh()


class CustomerDialog(QtWidgets.QDialog):
    """Create, edit, and archive customers."""

    def __init__(self, customers: CustomerRepository, parent: object = None) -> None:
        super().__init__(parent)
        self.customers = customers
        self.setWindowTitle("Manage customers")
        self.resize(520, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self.name_input = QtWidgets.QLineEdit(self)
        self.email_input = QtWidgets.QLineEdit(self)
        self.phone_input = QtWidgets.QLineEdit(self)
        self.notes_input = QtWidgets.QLineEdit(self)
        layout.addWidget(QtWidgets.QLabel("Name", self))
        layout.addWidget(self.name_input)
        layout.addWidget(QtWidgets.QLabel("Email", self))
        layout.addWidget(self.email_input)
        layout.addWidget(QtWidgets.QLabel("Phone", self))
        layout.addWidget(self.phone_input)
        layout.addWidget(QtWidgets.QLabel("Notes", self))
        layout.addWidget(self.notes_input)
        add_button = QtWidgets.QPushButton("Add customer", self)
        add_button.clicked.connect(self._add)
        edit_button = QtWidgets.QPushButton(EDIT_SELECTED_TEXT, self)
        edit_button.clicked.connect(self._edit)
        layout.addWidget(add_button)
        layout.addWidget(edit_button)
        self.customer_list = QtWidgets.QListWidget(self)
        layout.addWidget(self.customer_list)
        archive_button = QtWidgets.QPushButton(ARCHIVE_SELECTED_TEXT, self)
        archive_button.clicked.connect(self._archive)
        layout.addWidget(archive_button)
        close_button = QtWidgets.QPushButton(CLOSE_TEXT, self)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        self._refresh()

    def _refresh(self) -> None:
        self.customer_list.clear()
        for customer in self.customers.list_active():
            item = QtWidgets.QListWidgetItem(
                f"{customer.name} ({customer.email or customer.phone or NO_CONTACT_TEXT}) "
                f"- {customer.transaction_count} transactions",
                self.customer_list,
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, customer.id)

    def _add(self) -> None:
        try:
            self.customers.create(
                self.name_input.text(),
                self.email_input.text(),
                self.phone_input.text(),
                self.notes_input.text(),
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not add customer", str(error))
            return
        self.name_input.clear()
        self.email_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        self._refresh()

    def _edit(self) -> None:
        item = self.customer_list.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(self, "No customer selected", "Select a customer first.")
            return
        try:
            self.customers.update(
                item.data(QtCore.Qt.ItemDataRole.UserRole),
                self.name_input.text(),
                self.email_input.text(),
                self.phone_input.text(),
                self.notes_input.text(),
            )
        except (ValueError, LookupError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not edit customer", str(error))
            return
        self.name_input.clear()
        self.email_input.clear()
        self.phone_input.clear()
        self.notes_input.clear()
        self._refresh()

    def _archive(self) -> None:
        item = self.customer_list.currentItem()
        if item is not None:
            self.customers.archive(item.data(QtCore.Qt.ItemDataRole.UserRole))
            self._refresh()


class MovementHistoryDialog(QtWidgets.QDialog):
    """Display stock movements with audit filters for product and movement type."""

    def __init__(
        self,
        products: ProductRepository,
        movements: MovementRepository,
        parent: object = None,
        product_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.products = products
        self.movements = movements
        self.product_id = product_id
        self.suppliers = SupplierRepository(products.connection)
        self.customers = CustomerRepository(products.connection)
        self._export_threads: list[Any] = []
        self._export_rows: list[tuple[str, ...]] = []
        self.setWindowTitle("Stock movement history")
        self.resize(900, 420)
        self._build_form()

    def _build_form(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        filters = QtWidgets.QHBoxLayout()
        self.product_filter = QtWidgets.QComboBox(self)
        self.product_filter.addItem(ALL_PRODUCTS_TEXT, None)
        for product in self.products.list_active():
            self.product_filter.addItem(f"{product.sku} - {product.name}", product.id)
        if self.product_id is not None:
            product_index = self.product_filter.findData(self.product_id)
            if product_index >= 0:
                self.product_filter.setCurrentIndex(product_index)
        self.type_filter = QtWidgets.QComboBox(self)
        self.type_filter.addItem(ALL_TYPES_TEXT, None)
        for movement_type in ("receive", "issue", "adjustment"):
            self.type_filter.addItem(movement_type.title(), movement_type)
        self.supplier_filter = QtWidgets.QComboBox(self)
        self.supplier_filter.addItem(ALL_SUPPLIERS_TEXT, None)
        for supplier in self.suppliers.list_active():
            self.supplier_filter.addItem(supplier.name, supplier.id)
        self.customer_filter = QtWidgets.QComboBox(self)
        self.customer_filter.addItem(ALL_CUSTOMERS_TEXT, None)
        for customer in self.customers.list_active():
            self.customer_filter.addItem(customer.name, customer.id)
        self.start_date = QtWidgets.QDateEdit(self)
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QtCore.QDate.currentDate().addDays(-30))
        self.end_date = QtWidgets.QDateEdit(self)
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QtCore.QDate.currentDate())
        filters.addWidget(QtWidgets.QLabel("Product", self))
        filters.addWidget(self.product_filter)
        filters.addWidget(QtWidgets.QLabel("Type", self))
        filters.addWidget(self.type_filter)
        filters.addWidget(QtWidgets.QLabel("Supplier", self))
        filters.addWidget(self.supplier_filter)
        filters.addWidget(QtWidgets.QLabel("Customer", self))
        filters.addWidget(self.customer_filter)
        filters.addWidget(QtWidgets.QLabel("From", self))
        filters.addWidget(self.start_date)
        filters.addWidget(QtWidgets.QLabel("To", self))
        filters.addWidget(self.end_date)
        refresh_button = QtWidgets.QPushButton(REFRESH_TEXT, self)
        refresh_button.clicked.connect(self._refresh)
        filters.addWidget(refresh_button)
        export_button = QtWidgets.QPushButton(EXPORT_CSV_TEXT, self)
        export_button.clicked.connect(self._export_csv)
        filters.addWidget(export_button)
        layout.addLayout(filters)

        self.table = QtWidgets.QTableWidget(0, 9, self)
        self.table.setHorizontalHeaderLabels(
            [
                "Date",
                "Product",
                "Type",
                "Qty",
                "Previous",
                "Result",
                "Supplier",
                "Customer",
                "Reason",
            ]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        close_button = QtWidgets.QPushButton(CLOSE_TEXT, self)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self._refresh()

    def _refresh(self) -> None:
        product_id = self.product_filter.currentData()
        movement_type = self.type_filter.currentData()
        supplier_id = self.supplier_filter.currentData()
        customer_id = self.customer_filter.currentData()
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        rows = self.movements.list_history(
            product_id=product_id,
            movement_type=movement_type,
            start_date=start_date,
            end_date=end_date,
            supplier_id=supplier_id,
            customer_id=customer_id,
        )
        self._export_rows = [
            (
                row.created_at or "",
                f"{row.sku} - {row.product_name}",
                row.movement_type,
                str(row.quantity),
                str(row.previous_quantity),
                str(row.resulting_quantity),
                row.supplier_name or "",
                row.customer_name or "",
                row.reason or "",
            )
            for row in rows
        ]
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values: list[object] = [
                row.created_at or "",
                f"{row.sku} - {row.product_name}",
                row.movement_type,
                row.quantity,
                row.previous_quantity,
                row.resulting_quantity,
                row.supplier_name or "-",
                row.customer_name or "-",
                row.reason or "-",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(str(value)))

    def _export_csv(self) -> None:
        """Export the currently filtered movement history to a CSV file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export movement history", "movement-history.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        self._start_csv_export(path)

    def _start_csv_export(self, path: str) -> None:
        """Write the currently displayed movement rows on a worker thread."""
        thread = QtCore.QThread(self)
        worker = CsvExportWorker(
            path,
            (
                "date",
                "product",
                "type",
                "quantity",
                "previous_quantity",
                "resulting_quantity",
                "supplier",
                "customer",
                "reason",
            ),
            self._export_rows,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._export_finished)
        worker.failed.connect(self._export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._export_threads.remove(thread))
        self._export_threads.append(thread)
        thread.start()

    def _export_finished(self, path: str) -> None:
        """Notify the user after movement history export succeeds."""
        QtWidgets.QMessageBox.information(self, "Export complete", f"Movement history was exported to {path}.")

    def _export_failed(self, message: str) -> None:
        """Show a recoverable movement export error."""
        QtWidgets.QMessageBox.critical(
            self, "Export failed", f"Movement history could not be exported.\n\n{message}"
        )


class GoogleSheetsDialog(QtWidgets.QDialog):
    """Load, edit, and commit staged changes across all spreadsheet tabs."""

    def __init__(self, connection: sqlite3.Connection, parent: object = None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.import_service = SpreadsheetImportService(connection)
        self.client: GoogleSheetsClient | None = None
        self.spreadsheet_id = ""
        self.original_tables: tuple[SheetTable, ...] = ()
        self.tables: dict[str, Any] = {}
        credentials_file, spreadsheet_url = google_sheets_settings()
        self.setWindowTitle("Google Sheets sync")
        self.resize(1000, 650)
        self._build_form()
        self.credentials_input.setText(credentials_file)
        self.spreadsheet_input.setText(spreadsheet_url)

    def _build_form(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.credentials_input = QtWidgets.QLineEdit(self)
        credentials_button = QtWidgets.QPushButton("Choose JSON", self)
        credentials_button.clicked.connect(self._choose_credentials)
        credentials_row = QtWidgets.QHBoxLayout()
        credentials_row.addWidget(self.credentials_input)
        credentials_row.addWidget(credentials_button)
        form.addRow("Service-account JSON", credentials_row)
        self.spreadsheet_input = QtWidgets.QLineEdit(self)
        form.addRow("Spreadsheet URL or ID", self.spreadsheet_input)
        layout.addLayout(form)

        actions = QtWidgets.QHBoxLayout()
        self.load_button = QtWidgets.QPushButton(LOAD_SHEETS_TEXT, self)
        self.load_button.clicked.connect(self._load)
        self.commit_button = QtWidgets.QPushButton(COMMIT_SHEETS_TEXT, self)
        self.commit_button.setEnabled(False)
        self.commit_button.clicked.connect(self._commit)
        self.import_button = QtWidgets.QPushButton("Import inventory", self)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import_inventory)
        actions.addWidget(self.load_button)
        actions.addWidget(self.commit_button)
        actions.addWidget(self.import_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QtWidgets.QLabel("No spreadsheet loaded", self)
        layout.addWidget(self.status)
        self.tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self.tabs)
        close_button = QtWidgets.QPushButton(CLOSE_TEXT, self)
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)

    def _choose_credentials(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose service-account JSON", "", "JSON files (*.json)"
        )
        if path:
            self.credentials_input.setText(path)

    def _load(self) -> None:
        credentials_path = self.credentials_input.text().strip()
        spreadsheet_value = self.spreadsheet_input.text().strip()
        if not credentials_path or not spreadsheet_value:
            QtWidgets.QMessageBox.warning(
                self, "Missing configuration", "Credentials and spreadsheet ID are required."
            )
            return
        try:
            spreadsheet_id = spreadsheet_id_from_url(spreadsheet_value)
            self.client = GoogleSheetsClient.from_service_account(Path(credentials_path))
            self.original_tables = self.client.read_all_tabs(spreadsheet_id)
        except (GoogleSheetsError, ValueError) as error:
            QtWidgets.QMessageBox.critical(self, "Could not load spreadsheet", str(error))
            return
        self.spreadsheet_id = spreadsheet_id
        self._populate_tabs(self.original_tables)
        self.commit_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.status.setText(f"Loaded {len(self.original_tables)} tabs. Changes are staged locally.")

    def _import_inventory(self) -> None:
        """Preview recognized inventory tabs and commit them after confirmation."""
        try:
            plan = self.import_service.preview(self.original_tables)
        except SpreadsheetImportError as error:
            QtWidgets.QMessageBox.critical(self, "Could not prepare import", str(error))
            return
        summary = (
            f"Categories: {len(plan.categories)}\n"
            f"Suppliers: {len(plan.suppliers)}\n"
            f"Customers: {len(plan.customers)}\n"
            f"Products: {len(plan.products)}"
        )
        if plan.warnings:
            summary += "\n\n" + "\n".join(plan.warnings)
        answer = QtWidgets.QMessageBox.question(
            self,
            "Import inventory from spreadsheet",
            f"Commit this inventory import?\n\n{summary}",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.import_service.commit(plan)
        except (SpreadsheetImportError, sqlite3.DatabaseError) as error:
            QtWidgets.QMessageBox.critical(self, "Import failed", str(error))
            return
        self.status.setText("Inventory import committed successfully.")

    def _populate_tabs(self, tables: tuple[SheetTable, ...]) -> None:
        self.tabs.clear()
        self.tables.clear()
        for sheet in tables:
            rows = max(1, len(sheet.values))
            columns = max(1, max((len(row) for row in sheet.values), default=0))
            table = QtWidgets.QTableWidget(rows, columns, self.tabs)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked)
            for row_index, values in enumerate(sheet.values):
                for column_index, value in enumerate(values):
                    table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
            self.tables[sheet.title] = table
            self.tabs.addTab(table, sheet.title)

    def _current_tables(self) -> tuple[SheetTable, ...]:
        """Read all editable tab widgets into staged snapshots."""
        snapshots: list[SheetTable] = []
        for title, table in self.tables.items():
            values: list[tuple[str, ...]] = []
            for row in range(table.rowCount()):
                values.append(
                    tuple(
                        table.item(row, column).text() if table.item(row, column) else ""
                        for column in range(table.columnCount())
                    )
                )
            snapshots.append(SheetTable(title, tuple(values)))
        return tuple(snapshots)

    def _commit(self) -> None:
        """Commit staged cell changes after showing the pending change count."""
        if self.client is None:
            return
        changes = diff_tables(self.original_tables, self._current_tables())
        if not changes:
            self.status.setText("No changes to commit.")
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Commit spreadsheet changes",
            f"Commit {len(changes)} changed cells across the loaded tabs?",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.client.commit(self.spreadsheet_id, changes)
        except GoogleSheetsError as error:
            QtWidgets.QMessageBox.critical(self, "Commit failed", str(error))
            return
        self.original_tables = self._current_tables()
        self.status.setText(f"Committed {len(changes)} changed cells.")


class SchemaDialog(QtWidgets.QDialog):
    """Collect a validated table definition from an administrator."""

    def __init__(self, connection: sqlite3.Connection, parent: object = None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.setWindowTitle("Add custom table")
        self.resize(760, 360)
        self._build_form()

    def _build_form(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self.table_name_input = QtWidgets.QLineEdit(self)
        layout.addWidget(QtWidgets.QLabel("Table name", self))
        layout.addWidget(self.table_name_input)
        self.columns = QtWidgets.QTableWidget(0, 5, self)
        self.columns.setHorizontalHeaderLabels(
            ["Column", "Type", "Primary key", "Foreign table", "Foreign column"]
        )
        layout.addWidget(self.columns)
        row_actions = QtWidgets.QHBoxLayout()
        add_column = QtWidgets.QPushButton(ADD_COLUMN_TEXT, self)
        remove_column = QtWidgets.QPushButton(REMOVE_COLUMN_TEXT, self)
        add_column.clicked.connect(self._add_column)
        remove_column.clicked.connect(self._remove_column)
        row_actions.addWidget(add_column)
        row_actions.addWidget(remove_column)
        row_actions.addStretch()
        layout.addLayout(row_actions)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._add_column()

    def _add_column(self) -> None:
        row = self.columns.rowCount()
        self.columns.insertRow(row)
        self.columns.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        type_input = QtWidgets.QComboBox(self)
        type_input.addItems(["TEXT", "INTEGER", "REAL", "NUMERIC"])
        self.columns.setCellWidget(row, 1, type_input)
        primary_input = QtWidgets.QCheckBox(self)
        self.columns.setCellWidget(row, 2, primary_input)
        self.columns.setItem(row, 3, QtWidgets.QTableWidgetItem(""))
        self.columns.setItem(row, 4, QtWidgets.QTableWidgetItem(""))

    def _remove_column(self) -> None:
        row = self.columns.currentRow()
        if row >= 0:
            self.columns.removeRow(row)

    def _save(self) -> None:
        columns: list[ColumnDefinition] = []
        for row in range(self.columns.rowCount()):
            name = self.columns.item(row, 0)
            foreign_table = self.columns.item(row, 3)
            foreign_column = self.columns.item(row, 4)
            type_input = self.columns.cellWidget(row, 1)
            primary_input = self.columns.cellWidget(row, 2)
            columns.append(
                ColumnDefinition(
                    name.text().strip() if name else "",
                    type_input.currentText(),
                    primary_input.isChecked(),
                    foreign_table.text().strip() if foreign_table else None,
                    foreign_column.text().strip() if foreign_column else None,
                )
            )
        try:
            create_custom_table(self.connection, self.table_name_input.text(), columns)
        except (ValueError, sqlite3.DatabaseError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not create table", str(error))
            return
        self.accept()


class LoginDialog(QtWidgets.QDialog):
    """Authenticate a user before opening the application."""

    def __init__(self, connection: sqlite3.Connection, parent: object = None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.session: UserSession | None = None
        self.resize(350, 150)
        self.setWindowTitle("Sign in")
        layout = QtWidgets.QFormLayout(self)
        self.username_input = QtWidgets.QLineEdit(self)
        self.password_input = QtWidgets.QLineEdit(self)
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        layout.addRow("Username", self.username_input)
        layout.addRow("Password", self.password_input)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        buttons.accepted.connect(self._login)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setFixedSize(350, 150)

    def _login(self) -> None:
        try:
            self.session = authenticate(
                self.connection, self.username_input.text(), self.password_input.text()
            )
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Sign in failed", str(error))
            return
        self.accept()


class UserDialog(QtWidgets.QDialog):
    """Create a user and assign one or more RBAC groups."""

    def __init__(
        self, connection: sqlite3.Connection, setup: bool = False, parent: object = None
    ) -> None:
        super().__init__(parent)
        self.connection = connection
        self.setWindowTitle("Create administrator" if setup else "Add user")
        layout = QtWidgets.QFormLayout(self)
        self.username_input = QtWidgets.QLineEdit(self)
        self.password_input = QtWidgets.QLineEdit(self)
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.groups_input = QtWidgets.QListWidget(self)
        self.groups_input.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        for group in list_groups(connection):
            item = QtWidgets.QListWidgetItem(group, self.groups_input)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                QtCore.Qt.CheckState.Checked
                if setup and group == "Administrator"
                else QtCore.Qt.CheckState.Unchecked
            )
        if setup:
            self.groups_input.setEnabled(False)
        layout.addRow("Username", self.username_input)
        layout.addRow("Password", self.password_input)
        layout.addRow("Groups", self.groups_input)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        groups = [
            self.groups_input.item(index).text()
            for index in range(self.groups_input.count())
            if self.groups_input.item(index).checkState() == QtCore.Qt.CheckState.Checked
        ]
        try:
            create_user(
                self.connection,
                self.username_input.text(),
                self.password_input.text(),
                groups,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not create user", str(error))
            return
        self.accept()
