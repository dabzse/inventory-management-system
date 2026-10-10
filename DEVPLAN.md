# Inventory and Stock Management System - Development Plan

## 1. Goal

Build a desktop inventory and stock management application using Python, PySide6, and SQLite.

The first release should support:

- Product and category management
- Suppliers and customers
- Stock receiving and stock issuing
- Stock adjustments and movement history
- Current stock levels and low-stock alerts
- Search, filtering, and basic reports
- Local SQLite storage with reliable validation and backups

## 2. Proposed Technology

- Python 3.11+
- PySide6 for the desktop UI
- SQLite for local persistence
- Python `sqlite3` module for database access
- `pytest` for tests
- `ruff` for linting and formatting
- `pyrefly` for type hints analysis
  - `mypy` or `Pyright` for optional type checking
- `Git` for version control

## 3. Architecture

Use a layered structure so the UI does not contain database or stock calculation logic.

```text
ims/
  app.py                 # Application entry point
  config.py              # Paths and application settings
  database/
    connection.py        # SQLite connection and transactions
    migrations.py        # Schema creation and upgrades
  models/                # Typed domain objects
  repositories/          # SQL queries and persistence
  services/              # Business rules and transactions
  ui/
    main_window.py
    dialogs/
    widgets/
    views/
  reports/               # Export and report generation
  utils/
  tests/
```

Primary dependency direction:

```text
UI -> Services -> Repositories -> SQLite
```

The UI should call services, while services enforce business rules and repositories handle SQL.

## 4. Domain Rules

- Every product has a unique SKU.
- Stock quantity cannot become negative unless negative stock is explicitly enabled in settings.
- Every stock change creates an immutable stock movement record.
- Receiving stock increases quantity.
- Issuing stock decreases quantity.
- Adjustments record both the old quantity and the new quantity.
- Deleting a product with stock history should be prevented; archive it instead.
- Monetary values should be stored as integer minor units, such as cents, or as validated decimals.
- All user input must be validated before it reaches the database.
- Stock-changing operations must run inside a database transaction.

## 5. Task Breakdown

### Phase 0 - Project Setup

- [x] Create the Python package and directory structure.
- [x] Add `pyproject.toml` with runtime and development dependencies.
- [x] Add a minimal `app.py` that starts a PySide6 application.
- [x] Add `.gitignore` for Python, virtual environments, SQLite files, and IDE files.
- [x] Add a `README.md` with setup and run instructions.
- [x] Configure `pytest` and `ruff`; add Pyright workspace configuration.
- [x] Create a development database path outside the source package.

**Done when:** the application opens an empty main window and tests/linting run successfully.

### Phase 1 - Database Foundation

- [x] Implement SQLite connection creation with foreign keys enabled.
- [x] Add transaction helpers for commit and rollback.
- [x] Add schema migration support with a schema version table.
- [x] Create the complete initial tables:
  - [x] `categories`
  - [x] `products`
  - [x] `suppliers`
  - [x] `customers`
  - [x] `stock_movements`
  - [x] `settings`
- [x] Add indexes for SKU, product name, movement date, and movement type.
- [x] Add seed data for development only. (RBAC groups and permissions.)
- [x] Add database initialization and backup helpers.

**Done when:** a fresh database can be created repeatedly and all constraints work in automated tests.

### Phase 2 - Domain Models and Repositories

- [x] Define a typed model for products; add remaining entity models as their tables are introduced.
- [x] Implement repository methods for create, read, update, archive, and search operations.
- [x] Use parameterized SQL for every query.
- [x] Return domain objects instead of SQLite row details to the UI.
- [x] Add pagination or limited result queries for large product lists.
- [x] Add repository tests using a temporary SQLite database.

**Done when:** repositories can persist and retrieve all core entities without UI code.

### Phase 3 - Inventory Services

- [x] Implement a stock service for receiving stock.
- [x] Implement a stock service for issuing stock.
- [x] Implement stock adjustment with a required reason.
- [x] Transfer support is not required for the current single-location deployment.
- [x] Calculate current quantity from a maintained quantity field plus movement records.
- [x] Reject missing products and insufficient stock; expand quantity validation with the adjustment workflow.
- [x] Make each stock operation atomic.
- [x] Add low-stock and out-of-stock queries. (Low-stock filtering is implemented; out-of-stock remains a future refinement.)
- [x] Add service-level tests for successful and rejected operations.

**Done when:** every stock change is validated, transactional, and traceable in movement history.

### Phase 4 - Main Window and Navigation

- [x] Create the main window with a central product table.
- [x] Add product creation and receive/issue stock dialogs.
- [x] Add navigation for Dashboard, Products, Stock Operations, Suppliers, Customers, and Reports.
- [x] Restructure the main navigation into Manage Stock, Manage Users, Search, and About menus with contextual secondary actions.
- [x] Add validation and error dialogs for the initial product and stock workflows.
- [x] Add application settings such as database location and negative-stock policy.
- [x] Ensure long-running exports or maintenance actions do not freeze the UI. (CSV, PDF, and scheduled backup work run in background workers.)

**Done when:** a user can navigate between all planned modules from one main window.

### Phase 5 - Product and Category Management

- [x] Build the category list and create/edit/archive dialog.
- [x] Build the product list with SKU, name, category, quantity, and reorder level.
- [x] Add a product create form.
- [x] Add SKU uniqueness validation through the database constraint and UI error handling.
- [x] Add search and low-stock filtering.
- [x] Add category filtering.
- [x] Add archive behavior instead of destructive deletion.
- [x] Refresh views after changes without restarting the application.

**Done when:** users can maintain the product catalog and quickly identify products needing replenishment.

### Phase 6 - Stock Operations UI

- [x] Build an initial receiving-stock form with product, quantity, and reason fields.
- [x] Build an initial issuing-stock form with product, quantity, and reason fields.
- [x] Build an adjustment form with new quantity and mandatory reason.
- [x] Show the resulting quantity before confirmation.
- [x] Display clear validation messages through the initial dialogs.
- [x] Disable submission while an operation is being saved.
- [x] Refresh stock data after successful completion.

**Done when:** a user can complete receive, issue, and adjustment workflows without editing the database directly.

### Phase 7 - Movement History and Auditability

- [x] Build a stock movement table with date, product, type, quantity, supplier/customer source, and reason.
- [x] Add filters for date range, product, movement type, supplier, and customer.
- [x] Add a product history view.
- [x] Prevent editing or deleting completed movement records.
- [x] Add export of filtered movement history to CSV.

**Done when:** users can explain how any product reached its current stock quantity.

### Phase 8 - Suppliers and Customers

- [x] Implement supplier CRUD and archive behavior.
- [x] Implement customer CRUD and archive behavior.
- [x] Add contact fields and notes.
- [x] Link suppliers to receiving operations.
- [x] Link customers to issuing operations.
- [x] Add related transaction counts or history views where useful.

**Done when:** stock transactions can be associated with the relevant business partner.

### Phase 9 - Dashboard and Reports

- [x] Add dashboard totals for products, total stock units, low-stock products, and recent movements.
- [x] Add low-stock report.
- [x] Stock valuation report deferred because product cost data is not currently available.
- [x] Add movement summary by date and type.
- [x] Add CSV export for tabular reports.
- [x] Add print-friendly or PDF export only after CSV reporting is stable.
- [x] Add multi-tab Google Sheets sync with staged cell-level commits.
- [x] Add bootstrap import that creates inventory records from recognized spreadsheet tabs.

**Done when:** the application provides useful operational information without requiring SQL knowledge.

### Phase 10 - Reliability and Security

- [x] Add automatic database backup before migrations and on configurable schedule. (Migration backups and opt-in `backup_interval_hours` scheduling are implemented.)
- [x] Add restore validation and clear backup error messages.
- [x] Handle database locks, disk-full errors, and corrupted database errors gracefully. (Startup errors show a clear dialog.)
- [x] Add structured application logging without logging sensitive data.
- [x] Confirm all SQL uses parameters. (Dynamic identifiers are validated before SQL construction.)
- [x] Add safe shutdown handling and unsaved-form prompts. (Application exit confirmation added; modal forms cancel unsaved edits.)
- [x] Add password protection and RBAC for deployments requiring multiple users.

**Done when:** common storage and application failures produce recoverable behavior and understandable messages.

### Phase 11 - Testing and Quality

- [x] Add unit tests for validation and stock business rules.
- [x] Add repository tests against temporary databases.
- [x] Add service tests for transaction rollback behavior.
- [x] Add focused UI tests for critical forms where practical. (Stock receiving dialog coverage added.)
- [x] Test empty states, duplicate SKUs, zero quantities, decimal values, and large quantities.
- [x] Test database migration from an older schema version.
- [x] Run linting, type checking, and tests in one command.
- [ ] Manually test the complete receive-to-issue workflow. (Automated offscreen UI coverage now validates receive followed by issue; manual desktop smoke test remains.)

**Done when:** the critical workflows are covered and the project has a repeatable quality check.

### Phase 12 - Packaging and Release

- [x] Add application version information.
- [x] Choose PyInstaller as the packaging tool.
- [x] Package the application for Linux with PyInstaller and provide Linux, Windows, and macOS build workflows; non-Linux artifact verification remains a separate target build.
- [x] Verify the Linux packaged application creates and locates its database correctly. (Windows verification remains part of the Windows target build.)
- [x] Include migration, backup, and restore behavior in packaged-path tests. (Windows executable coverage remains part of the Windows target build.)
- [x] Write a short user guide. (See `USER_GUIDE.md`.)
- [x] Create a release checklist and backup warning for users. (See `RELEASE_CHECKLIST.md`.)

**Done when:** a non-developer can install, open, back up, and use the application.

## 6. Suggested Milestones

### Milestone 1 - Usable Catalog

Complete Phases 0-2 and the product/category parts of Phase 5.

Result: users can maintain a product catalog in a persistent database.

### Milestone 2 - Working Inventory

Complete Phase 3 and Phase 6.

Result: users can receive, issue, and adjust stock with transactional history.

### Milestone 3 - Operational Release

Complete Phases 4, 7, 8, and 9.

Result: users can operate the inventory system and produce basic reports.

### Milestone 4 - Production Readiness

Complete Phases 10-12.

Result: the application is tested, backed up, packaged, and documented.

## 7. First Implementation Slice

Start with the smallest end-to-end workflow:

1. [x] Create the project structure and test configuration.
2. [x] Create the SQLite schema for categories, products, and stock movements.
3. [x] Implement product repository operations.
4. [x] Implement receiving and issuing services.
5. [x] Build a product table and stock-operation dialogs.
6. [x] Add tests for stock increase, stock decrease, insufficient stock, and rollback.

This slice validates the architecture early and provides a usable inventory core before adding secondary modules.

### Current Implementation Status

The current implementation includes the Python package, venv-based setup, a project-local SQLite database, bootstrap authentication tables for new installations, migration-backed inventory tables, persisted application settings including the negative-stock policy and local/shared database selection through `settings.ini`, opt-in scheduled backups, seeded Administrator/Manager/Viewer RBAC groups, password authentication with user-to-group assignment, validated custom table creation with PK/FK metadata, category persistence and create/edit/archive management, category-linked products with search and filtering, receiving and issuing services with transactional movement records and supplier/customer links, adjustment services, supplier/customer CRUD dialogs, immutable movement-history tables with date, product, type, supplier, and customer filters, product history, CSV and PDF exports, multi-tab Google Sheets sync with staged cell-level commits, spreadsheet bootstrap import with preview warnings, a compact contextual PySide6 navigation with right-aligned signed-in user information, a PySide6 product table, initial product and stock-operation dialogs, focused UI coverage for receiving and receive-to-issue workflows, a verified Linux PyInstaller build, verified Linux packaged-database initialization, configured-path migration, backup, and restore coverage, a short user guide, and a release checklist with backup warnings. Stock valuation is deferred until product cost data exists; Windows packaging and a manual desktop smoke test remain planned; transfer support is intentionally deferred because the current deployment has one location.

## 8. Definition of Done

A task is complete when:

- Its behavior is implemented in the appropriate layer.
- Invalid input has a defined result.
- The database operation is parameterized and transactional where needed.
- Relevant automated tests exist.
- The UI gives clear success and failure feedback when applicable.
- The change is documented if it affects setup, schema, or user workflow.
- `pytest`, linting, and type checks pass for the current project.
