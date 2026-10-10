# Inventory and Stock Management System

A desktop inventory application built with Python, PySide6, and SQLite.

See [USER_GUIDE.md](USER_GUIDE.md) for first-start, stock-operation, database,
backup, and packaging instructions.

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before distributing a build.

## Setup

The best practice is to create a virtual environment, it avoids conflicts between different projects.

```bash
python3 -m venv venv
```

Activate it:

**Linux / macOS:**

```bash
source venv/bin/activate
```

**Windows:**

```bash
venv\Scripts\activate
```

Then, if you wanna install only the runtime dependencies, run:

```bash
pip install .
```

If you wanna install dev dependencies, then run:

```bash
pip install -e '.[dev]'
```

## Running the app

```bash
python ims/app.py
```

or

```bash
python -m ims
```

> **Warning:** First run will ask you to create an **admin** account: username and password; then to log in...

## Database

The development database is created at `database/inventory.sqlite3`.

New installations bootstrap with users, roles, permissions, settings, and
schema metadata. Inventory tables are populated from the committed spreadsheet
import rather than seeded with sample inventory data.

## Database location

The application initializes its SQLite database automatically on startup and creates a local database file at `database/inventory.sqlite3`.

Helpers are available in `ims.database.connection`:

- `initialize_database(path)` ensures the database file and schema exist
- `connect(path)` opens the initialized database connection
- `backup_database(path, backup_path=None)` creates a SQLite backup copy

## Check

```bash
./scripts/check.sh
```

The check script runs the test suite, Ruff, and Pyrefly in sequence.

## Packaging

PyInstaller is the selected packaging tool. After installing the development
dependencies, build the desktop executable with:

```bash
venv/bin/pyinstaller ims.spec
```

The generated executable is platform-specific:

- On Linux, the build creates `dist/ims`.
- On Windows, the build creates `dist/ims.exe`.
- On macOS, the build creates `dist/ims`.

PyInstaller does not normally cross-compile between Linux and Windows, so run
the build on each target operating system. The `.pkg` file created during the
build is an intermediate archive, not the final executable.

The Linux, Windows, and macOS build workflows are available at
`.github/workflows/build-linux.yml`,
`.github/workflows/build-windows.yml`, and
`.github/workflows/build-macos.yml`. They can be started manually from GitHub
Actions or run when a version tag such as `v1.0.0` is pushed. The manual
PyInstaller command above remains available for local builds.

### Database Location

The application reads `settings.ini` from the project directory during
development or beside the packaged executable. Select the database mode in the
`[database]` section:

```ini
[database]
database_location = local
```

`local` uses the platform's writable per-user data directory for packaged
builds. To use a shared or network database, configure an explicit path:

```ini
[database]
database_location = shared
database_path = /path/to/shared/inventory.sqlite3
```

Use a Windows path such as `\\server\share\inventory.sqlite3` when configuring
a Windows shared database. The shared SQLite file must be on storage that
supports reliable file locking, and simultaneous multi-user access should be
used cautiously.

### Google Sheets Sync

The Reports menu includes **Google Sheets sync**. It reads every tab in the
spreadsheet, displays the tabs separately for local editing, and sends only
changed cells when **Commit changes** is confirmed.

Before using it:

1. Enable the Google Sheets API in the Google Cloud project.
2. Create a service-account JSON key.
3. Share the spreadsheet with the service account's email address.
4. Enter the JSON key path and spreadsheet ID in the sync dialog.

The service-account JSON file is used locally and is not stored in the
application database. Keep it outside source control.

You can preconfigure the sync dialog in `settings.ini`:

```ini
[google_sheets]
credentials_file = /path/to/service-account.json
spreadsheet_url = https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit
```

The `spreadsheet_url` value may also be a raw spreadsheet ID.

> Note: I didn't test everything...
