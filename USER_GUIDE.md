# Inventory and Stock Management User Guide

## First Start

1. Start the application with `venv/bin/python -m ims` during development, or launch the packaged executable.
2. On first start, create the administrator account.
3. Sign in with the account you created.

New databases begin with authentication and settings tables. After signing in,
use **Reports > Google Sheets sync**, load the spreadsheet, and choose **Import
inventory** to create the inventory records from recognized tabs. The import
shows counts and warnings before committing.

Recognized tab names are `Categories`, `Suppliers`, `Customers`, and
`Products`. Product headers can include `SKU`, `Product` or `Name`, `Quantity`,
`Reorder Level`, and `Category`. Other tabs are left untouched and reported as
warnings.

## Products and Categories

Use the Products menu to:

- Add products with a unique SKU, name, category, and reorder level.
- Search by SKU, product name, or category.
- Filter to products at or below their reorder level.
- Edit or archive categories and products.

Archived products are retained for historical records and cannot be used for new stock operations.

## Stock Operations

Use Stock operations to receive, issue, or adjust stock:

- Receiving increases the product quantity and may include a supplier.
- Issuing decreases the product quantity and may include a customer.
- Adjustments set an exact quantity and require a reason.
- Every successful operation creates an immutable movement record.

Negative stock is blocked by default. The policy can be changed through the application settings stored in `settings.ini`.

Scheduled backups are disabled by default. To enable them, set the database
setting `backup_interval_hours` to a positive number, for example `24`, using
the application settings service. Backups are written to the local application's
`backups` directory even when the active database is shared.

## History and Reports

Stock history shows dates, products, movement types, quantities, previous and resulting quantities, partners, and reasons. Use the filters to review a product or date range, and export filtered history to CSV.

The Reports menu includes low-stock and movement-summary reports with CSV and PDF export options.

## Google Sheets Sync

Open **Reports > Google Sheets sync** to load all tabs from a spreadsheet. Each
tab is shown separately and edits remain local until you select **Commit
changes**. The dialog reports the number of changed cells and asks for
confirmation before writing them back.

The spreadsheet must be shared with the service account used by the JSON
credentials file. The Google Sheets API must also be enabled in that Google
Cloud project. Keep the credentials file private and outside source control.

To prefill the sync dialog, add these optional values to `settings.ini`:

```ini
[google_sheets]
credentials_file = /path/to/service-account.json
spreadsheet_url = https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit
```

The spreadsheet value can be either the full URL or the raw spreadsheet ID.

## Database Location

The default `settings.ini` uses local mode:

```ini
[database]
database_location = local
```

Packaged builds store local data in the platform's writable user-data directory. To use a shared database, provide an explicit path:

```ini
[database]
database_location = shared
database_path = /path/to/shared/inventory.sqlite3
```

Use shared SQLite storage only where reliable file locking is available. Keep regular backups before maintenance or migration work.

## Backups and Packaging

Database backups can be created with `backup_database()` from `ims.database.connection`. Validate restored files with `validate_database()` before using them.

PyInstaller builds are platform-specific:

- Linux: `dist/ims`
- Windows: `dist/ims.exe`

Build each target on its own operating system. The `.pkg` file produced during a build is an intermediate archive.
