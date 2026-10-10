"""Main product catalog window for the inventory application."""

import importlib
from collections import defaultdict
from typing import Any

from ims import __version__
from ims.repositories.categories import CategoryRepository
from ims.repositories.customers import CustomerRepository
from ims.repositories.movements import MovementRepository
from ims.repositories.products import ProductRepository
from ims.repositories.suppliers import SupplierRepository
from ims.services.access import UserSession, session_has_permission
from ims.services.stock import StockService
from ims.ui.dialogs import (
    CategoryDialog,
    CustomerDialog,
    GoogleSheetsDialog,
    MovementHistoryDialog,
    ProductDialog,
    SchemaDialog,
    StockDialog,
    SupplierDialog,
    UserDialog,
)
from ims.ui.export_worker import CsvExportWorker, PdfExportWorker

QtWidgets = importlib.import_module("PySide6.QtWidgets")
QtCore = importlib.import_module("PySide6.QtCore")

LOW_STOCK_REPORT_TITLE = "Low-stock report"
MOVEMENT_SUMMARY_TITLE = "Movement summary"
REORDER_LEVEL_LABEL = "Reorder level"


class MainWindow(QtWidgets.QMainWindow):
    """Display the active product catalog."""

    def __init__(
        self, products: ProductRepository, stock: StockService, session: UserSession
    ) -> None:
        """Create a product table backed by the given repository."""
        super().__init__()
        self.products = products
        self.stock = stock
        self.connection = products.connection
        self.categories = CategoryRepository(self.connection)
        self.suppliers = SupplierRepository(self.connection)
        self.customers = CustomerRepository(self.connection)
        self.session = session
        self._export_threads: list[Any] = []
        self.setWindowTitle("Inventory and Stock Management")
        self.resize(1024, 768)
        central_widget = QtWidgets.QWidget(self)
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        navigation = QtWidgets.QHBoxLayout()
        self.dashboard_button = QtWidgets.QPushButton("Dashboard", self)
        self.products_button = QtWidgets.QPushButton("Products", self)
        self.stock_operations_button = QtWidgets.QPushButton("Stock operations", self)
        self.suppliers_button = QtWidgets.QPushButton("Suppliers", self)
        self.customers_button = QtWidgets.QPushButton("Customers", self)
        self.reports_button = QtWidgets.QPushButton("Reports", self)
        self.manage_users_button = QtWidgets.QPushButton("Manage users", self)
        self.search_button = QtWidgets.QPushButton("Search", self)
        self.about_button = QtWidgets.QPushButton("About", self)
        self.navigation_group = QtWidgets.QButtonGroup(self)
        navigation_buttons = (
            self.dashboard_button,
            self.products_button,
            self.stock_operations_button,
            self.suppliers_button,
            self.customers_button,
            self.reports_button,
            self.manage_users_button,
            self.search_button,
            self.about_button,
        )
        for button in navigation_buttons:
            button.setCheckable(True)
            button.setStyleSheet(
                "QPushButton:checked { background-color: #2f6f9f; color: white; font-weight: bold; }"
            )
            self.navigation_group.addButton(button)
        self.dashboard_button.setChecked(True)
        self.signed_in_button = QtWidgets.QPushButton(self)
        self.signed_in_button.setText(f"Signed in: {session.username}")
        self.signed_in_button.setToolTip(
            f"Signed in as {session.username} ({', '.join(session.groups)})"
        )
        self.dashboard_button.clicked.connect(self.show_dashboard)
        self.products_button.clicked.connect(self.show_products_menu)
        self.stock_operations_button.clicked.connect(self.show_stock_operations_menu)
        self.suppliers_button.clicked.connect(self.manage_suppliers)
        self.customers_button.clicked.connect(self.manage_customers)
        self.reports_button.clicked.connect(self.show_reports_menu)
        self.manage_users_button.clicked.connect(self.show_users_menu)
        self.search_button.clicked.connect(self.show_search_menu)
        self.about_button.clicked.connect(self.show_about)
        self.signed_in_button.clicked.connect(self.show_session_info)
        navigation.addWidget(self.dashboard_button)
        navigation.addWidget(self.products_button)
        navigation.addWidget(self.stock_operations_button)
        navigation.addWidget(self.suppliers_button)
        navigation.addWidget(self.customers_button)
        navigation.addWidget(self.reports_button)
        navigation.addWidget(self.manage_users_button)
        navigation.addWidget(self.search_button)
        navigation.addWidget(self.about_button)
        navigation.addStretch()
        navigation.addWidget(self.signed_in_button)
        central_layout.addLayout(navigation)

        self.secondary_row = QtWidgets.QWidget(self)
        self.secondary_widget = self.secondary_row
        secondary = QtWidgets.QHBoxLayout(self.secondary_row)
        secondary.setContentsMargins(0, 0, 0, 0)
        self.secondary_layout = QtWidgets.QHBoxLayout()
        secondary.addLayout(self.secondary_layout)
        secondary.addStretch()
        central_layout.addWidget(self.secondary_row)

        self.add_product_button = QtWidgets.QPushButton("Add product", self)
        self.secondary_row.setMinimumHeight(self.add_product_button.sizeHint().height())
        self.receive_stock_button = QtWidgets.QPushButton("Receive stock", self)
        self.issue_stock_button = QtWidgets.QPushButton("Issue stock", self)
        self.adjust_stock_button = QtWidgets.QPushButton("Adjust stock", self)
        self.movement_history_button = QtWidgets.QPushButton("Stock history", self)
        self.product_history_button = QtWidgets.QPushButton("Product history", self)
        self.low_stock_report_button = QtWidgets.QPushButton(LOW_STOCK_REPORT_TITLE, self)
        self.movement_summary_button = QtWidgets.QPushButton(MOVEMENT_SUMMARY_TITLE, self)
        self.google_sheets_button = QtWidgets.QPushButton("Google Sheets sync", self)
        self.add_table_button = QtWidgets.QPushButton("Add custom table", self)
        self.add_user_button = QtWidgets.QPushButton("Manage users", self)
        self.manage_categories_button = QtWidgets.QPushButton("Manage categories", self)
        self.search_input = QtWidgets.QLineEdit(self)
        self.search_input.setPlaceholderText("Search SKU, product, or category")
        self.low_stock_filter = QtWidgets.QCheckBox("Low stock only", self)
        self.category_filter = QtWidgets.QComboBox(self)
        self.category_filter.addItem("All categories", None)
        for category in self.categories.list_active():
            self.category_filter.addItem(category.name, category.id)
        self.add_product_button.clicked.connect(self.add_product)
        self.receive_stock_button.clicked.connect(lambda: self.change_stock("receive"))
        self.issue_stock_button.clicked.connect(lambda: self.change_stock("issue"))
        self.adjust_stock_button.clicked.connect(lambda: self.change_stock("adjust"))
        self.movement_history_button.clicked.connect(self.show_movement_history)
        self.product_history_button.clicked.connect(self.show_product_history)
        self.low_stock_report_button.clicked.connect(self.show_low_stock_report)
        self.movement_summary_button.clicked.connect(self.show_movement_summary)
        self.google_sheets_button.clicked.connect(self.show_google_sheets)
        self.add_table_button.clicked.connect(self.add_custom_table)
        self.add_user_button.clicked.connect(self.add_user)
        self.manage_categories_button.clicked.connect(self.manage_categories)
        self.category_filter.currentIndexChanged.connect(self.refresh)
        self.search_input.textChanged.connect(self.refresh)
        self.low_stock_filter.stateChanged.connect(self.refresh)
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["SKU", "Product", "Category", "Stock", REORDER_LEVEL_LABEL]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        central_layout.addWidget(self.table)
        self.setCentralWidget(central_widget)
        self._update_permissions()
        self.refresh()
        self._clear_secondary_menu()

    def _clear_secondary_menu(self) -> None:
        """Remove the currently displayed secondary menu widgets."""
        for widget in self._context_widgets():
            widget.hide()
        while self.secondary_layout.count():
            self.secondary_layout.takeAt(0)
        self.secondary_row.show()

    def _context_widgets(self) -> tuple[Any, ...]:
        """Return controls that belong to a contextual secondary menu."""
        return (
            self.add_product_button,
            self.receive_stock_button,
            self.issue_stock_button,
            self.adjust_stock_button,
            self.movement_history_button,
            self.product_history_button,
            self.low_stock_report_button,
            self.movement_summary_button,
            self.google_sheets_button,
            self.add_table_button,
            self.add_user_button,
            self.manage_categories_button,
            self.search_input,
            self.category_filter,
            self.low_stock_filter,
        )

    def _add_context_widgets(self, widgets: tuple[Any, ...]) -> None:
        """Add and show the controls for the selected secondary menu."""
        for widget in widgets:
            self.secondary_layout.addWidget(widget)
            widget.show()
        self.secondary_row.show()

    def show_stock_menu(self) -> None:
        """Show product and stock-management actions in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets(
            (
                self.add_product_button,
                self.receive_stock_button,
                self.issue_stock_button,
                self.adjust_stock_button,
                self.movement_history_button,
                self.product_history_button,
                self.manage_categories_button,
            )
        )

    def show_products_menu(self) -> None:
        """Show product catalog actions in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets((self.add_product_button, self.manage_categories_button))

    def show_stock_operations_menu(self) -> None:
        """Show stock operation and history actions in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets(
            (
                self.receive_stock_button,
                self.issue_stock_button,
                self.adjust_stock_button,
                self.movement_history_button,
            )
        )

    def show_reports_menu(self) -> None:
        """Show report actions in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets(
            (
                self.movement_history_button,
                self.low_stock_report_button,
                self.movement_summary_button,
                self.google_sheets_button,
            )
        )

    def show_google_sheets(self) -> None:
        """Open the staged multi-tab Google Sheets synchronization dialog."""
        GoogleSheetsDialog(self.connection, self).exec()

    def show_low_stock_report(self) -> None:
        """Display active products at or below their reorder level."""
        products = self.products.search_active(low_stock=True)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(LOW_STOCK_REPORT_TITLE)
        dialog.resize(700, 420)
        layout = QtWidgets.QVBoxLayout(dialog)
        table = QtWidgets.QTableWidget(len(products), 4, dialog)
        table.setHorizontalHeaderLabels(["SKU", "Product", "Stock", REORDER_LEVEL_LABEL])
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        rows: list[tuple[str, ...]] = []
        for row_index, product in enumerate(products):
            values = (product.sku, product.name, str(product.quantity), str(product.reorder_level))
            rows.append(values)
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(table)
        actions = QtWidgets.QHBoxLayout()
        export_button = QtWidgets.QPushButton("Export CSV", dialog)
        export_button.clicked.connect(
            lambda: self._export_report_csv(
                "low-stock-report.csv",
                ("sku", "product", "stock", "reorder_level"),
                rows,
            )
        )
        actions.addWidget(export_button)
        pdf_button = QtWidgets.QPushButton("Export PDF", dialog)
        pdf_button.clicked.connect(
            lambda: self._export_report_pdf(
                LOW_STOCK_REPORT_TITLE, "low-stock-report.pdf", ("SKU", "Product", "Stock", REORDER_LEVEL_LABEL), rows
            )
        )
        actions.addWidget(pdf_button)
        close_button = QtWidgets.QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        dialog.exec()

    def show_movement_summary(self) -> None:
        """Display movement totals grouped by date and movement type."""
        grouped: defaultdict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for movement in MovementRepository(self.connection).list_history():
            date = (movement.created_at or "")[:10]
            totals = grouped[(date, movement.movement_type)]
            totals[0] += movement.quantity
            totals[1] += 1

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(MOVEMENT_SUMMARY_TITLE)
        dialog.resize(600, 400)
        layout = QtWidgets.QVBoxLayout(dialog)
        table = QtWidgets.QTableWidget(len(grouped), 4, dialog)
        table.setHorizontalHeaderLabels(["Date", "Type", "Quantity", "Movements"])
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        rows: list[tuple[str, ...]] = []
        for row_index, ((date, movement_type), (quantity, count)) in enumerate(
            sorted(grouped.items(), reverse=True)
        ):
            values = (date, movement_type, str(quantity), str(count))
            rows.append(values)
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(table)
        actions = QtWidgets.QHBoxLayout()
        export_button = QtWidgets.QPushButton("Export CSV", dialog)
        export_button.clicked.connect(
            lambda: self._export_report_csv(
                "movement-summary.csv", ("date", "type", "quantity", "movements"), rows
            )
        )
        actions.addWidget(export_button)
        pdf_button = QtWidgets.QPushButton("Export PDF", dialog)
        pdf_button.clicked.connect(
            lambda: self._export_report_pdf(
                MOVEMENT_SUMMARY_TITLE, "movement-summary.pdf", ("Date", "Type", "Quantity", "Movements"), rows
            )
        )
        actions.addWidget(pdf_button)
        close_button = QtWidgets.QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        dialog.exec()

    def _export_report_csv(
        self, default_name: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]
    ) -> None:
        """Export report headers and rows to a user-selected CSV file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export report", default_name, "CSV files (*.csv)"
        )
        if not path:
            return
        self._start_csv_export(path, headers, rows)

    def _start_csv_export(
        self, path: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]
    ) -> None:
        """Write prepared report rows on a worker thread."""
        thread = QtCore.QThread(self)
        worker = CsvExportWorker(path, headers, rows)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._report_export_finished)
        worker.failed.connect(self._report_export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._export_threads.remove(thread))
        self._export_threads.append(thread)
        thread.start()

    def _report_export_finished(self, path: str) -> None:
        """Notify the user after a background report export succeeds."""
        QtWidgets.QMessageBox.information(self, "Export complete", f"The report was exported to {path}.")

    def _report_export_failed(self, message: str) -> None:
        """Show a recoverable error when a background report export fails."""
        QtWidgets.QMessageBox.critical(self, "Export failed", f"The report could not be exported.\n\n{message}")

    def _export_report_pdf(
        self,
        title: str,
        default_name: str,
        headers: tuple[str, ...],
        rows: list[tuple[str, ...]],
    ) -> None:
        """Export report headers and rows to a user-selected PDF file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export report", default_name, "PDF files (*.pdf)"
        )
        if not path:
            return
        self._start_pdf_export(path, title, headers, rows)

    def _start_pdf_export(
        self,
        path: str,
        title: str,
        headers: tuple[str, ...],
        rows: list[tuple[str, ...]],
    ) -> None:
        """Render prepared report rows on a worker thread."""
        thread = QtCore.QThread(self)
        worker = PdfExportWorker(path, title, headers, rows)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._report_export_finished)
        worker.failed.connect(self._report_export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._export_threads.remove(thread))
        self._export_threads.append(thread)
        thread.start()

    def show_dashboard(self) -> None:
        """Display current inventory totals and recent movement activity."""
        self._clear_secondary_menu()
        product_count = self.connection.execute(
            "SELECT COUNT(*) FROM products WHERE archived = 0"
        ).fetchone()[0]
        total_units = self.connection.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM products WHERE archived = 0"
        ).fetchone()[0]
        low_stock_count = self.connection.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE archived = 0 AND quantity <= reorder_level"
        ).fetchone()[0]
        movement_count = self.connection.execute(
            "SELECT COUNT(*) FROM stock_movements"
        ).fetchone()[0]
        recent_movements = MovementRepository(self.connection).list_history()[-5:][::-1]
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Dashboard")
        dialog.setMinimumSize(700, 420)
        layout = QtWidgets.QVBoxLayout(dialog)
        summary = QtWidgets.QLabel(
            f"Active products: {product_count}\nTotal stock units: {total_units}\n"
            f"Low-stock products: {low_stock_count}\nRecorded movements: {movement_count}",
            dialog,
        )
        summary.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(summary)
        recent_table = QtWidgets.QTableWidget(len(recent_movements), 5, dialog)
        recent_table.setHorizontalHeaderLabels(["Date", "Product", "Type", "Quantity", "Reason"])
        recent_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        recent_table.horizontalHeader().setStretchLastSection(True)
        for row_index, movement in enumerate(recent_movements):
            values = (
                movement.created_at or "",
                f"{movement.sku} - {movement.product_name}",
                movement.movement_type,
                str(movement.quantity),
                movement.reason or "-",
            )
            for column_index, value in enumerate(values):
                recent_table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(recent_table)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok, parent=dialog
        )
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def show_users_menu(self) -> None:
        """Show user and schema administration actions in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets((self.add_user_button, self.add_table_button))

    def show_search_menu(self) -> None:
        """Show catalog search and filtering controls in the secondary row."""
        self._clear_secondary_menu()
        self._add_context_widgets(
            (self.search_input, self.category_filter, self.low_stock_filter)
        )
        self.search_input.setFocus()

    def show_about(self) -> None:
        """Display basic application information."""
        self._clear_secondary_menu()
        QtWidgets.QMessageBox.about(
            self,
            "About Inventory and Stock Management",
            f"Inventory and Stock Management\nVersion {__version__}\n\n"
            "A local inventory application powered by PySide6 and SQLite.",
        )

    def show_session_info(self) -> None:
        """Display the current user's account and role information."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Signed-in user")
        dialog.resize(350, 150)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(
            QtWidgets.QLabel(
                f"Username: {self.session.username}\nRoles: {', '.join(self.session.groups)}"
            )
        )
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok, parent=dialog
        )
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def close_event(self, event: Any) -> None:
        """Confirm application exit before the database connection is closed."""
        result = QtWidgets.QMessageBox.question(
            self,
            "Exit application",
            "Close the inventory application?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if result == QtWidgets.QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def add_product(self) -> None:
        """Open the product form and refresh after a successful save."""
        dialog = ProductDialog(self.products, self.categories, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.refresh()

    def change_stock(self, operation: str) -> None:
        """Open a receive or issue form and refresh after a successful save."""
        dialog = StockDialog(
            self.products,
            self.stock,
            operation,
            suppliers=self.suppliers,
            customers=self.customers,
            parent=self,
        )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.refresh()

    def show_movement_history(self) -> None:
        """Open the stock movement audit dialog."""
        MovementHistoryDialog(self.products, MovementRepository(self.connection), self).exec()

    def show_product_history(self) -> None:
        """Open movement history filtered to the selected product."""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QtWidgets.QMessageBox.warning(
                self, "No product selected", "Select a product before opening its history."
            )
            return
        sku = self.table.item(selected_row, 0)
        if sku is None:
            return
        products = self.products.search_active(sku.text())
        if not products:
            return
        MovementHistoryDialog(
            self.products,
            MovementRepository(self.connection),
            product_id=products[0].id,
            parent=self,
        ).exec()

    def add_custom_table(self) -> None:
        """Open the custom table builder for authorized groups."""
        dialog = SchemaDialog(self.connection, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            QtWidgets.QMessageBox.information(self, "Table created", "The custom table was created.")

    def add_user(self) -> None:
        """Open the user creation form for administrators."""
        UserDialog(self.connection, parent=self).exec()

    def manage_categories(self) -> None:
        """Open category management for users who can edit products."""
        CategoryDialog(self.categories, self).exec()
        self._reload_categories()
        self.refresh()

    def show_suppliers_menu(self) -> None:
        """Show supplier actions in the secondary row (currently empty)."""
        self._clear_secondary_menu()

    def show_customers_menu(self) -> None:
        """Show customer actions in the secondary row (currently empty)."""
        self._clear_secondary_menu()

    def manage_suppliers(self) -> None:
        """Open supplier management for authorized users."""
        self.show_suppliers_menu()
        SupplierDialog(self.suppliers, self).exec()

    def manage_customers(self) -> None:
        """Open customer management for authorized users."""
        self.show_customers_menu()
        CustomerDialog(self.customers, self).exec()

    def _reload_categories(self) -> None:
        selected = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories", None)
        for category in self.categories.list_active():
            self.category_filter.addItem(category.name, category.id)
        index = self.category_filter.findData(selected)
        self.category_filter.setCurrentIndex(max(index, 0))
        self.category_filter.blockSignals(False)

    def _update_permissions(self) -> None:
        """Apply the authenticated user's group permissions to available actions."""
        can_write = session_has_permission(self.session, self.connection, "product.write")
        can_stock = session_has_permission(self.session, self.connection, "stock.write")
        can_schema = session_has_permission(self.session, self.connection, "schema.create")
        can_manage_users = session_has_permission(self.session, self.connection, "rbac.manage")
        can_manage_categories = can_write
        self.add_product_button.setEnabled(can_write)
        self.receive_stock_button.setEnabled(can_stock)
        self.issue_stock_button.setEnabled(can_stock)
        self.adjust_stock_button.setEnabled(can_stock)
        self.movement_history_button.setEnabled(can_stock or can_write)
        self.product_history_button.setEnabled(can_stock or can_write)
        self.add_table_button.setEnabled(can_schema)
        self.add_user_button.setEnabled(can_manage_users)
        self.manage_categories_button.setEnabled(can_manage_categories)
        self.suppliers_button.setEnabled(can_write)
        self.customers_button.setEnabled(can_write)

    def refresh(self) -> None:
        """Reload active products into the table."""
        products = self.products.search_active(
            self.search_input.text(),
            self.category_filter.currentData(),
            self.low_stock_filter.isChecked(),
        )
        self.table.setRowCount(len(products))
        for row_index, product in enumerate(products):
            values = (
                product.sku,
                product.name,
                product.category_name or "-",
                str(product.quantity),
                str(product.reorder_level),
            )
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))


MainWindow.closeEvent = MainWindow.close_event
