# Release Checklist

## Before Building

- [ ] Run `./scripts/check.sh` with the target environment configured.
- [ ] Review pending database migrations and confirm a backup is available.
- [ ] Confirm `settings.ini` uses the intended `local` or `shared` database mode.
- [ ] Test the receive, issue, adjustment, history, and CSV export workflows.
- [ ] Confirm the user guide matches the current application behavior.

## Linux Release

- [ ] Build with `venv/bin/pyinstaller --clean --noconfirm ims.spec` on Linux.
- [ ] Confirm `dist/ims` is an executable Linux binary.
- [ ] Launch the packaged application and verify database initialization.
- [ ] Test the packaged application with a clean writable data directory.

## Windows Release

- [ ] Build on Windows with the Windows Python environment.
- [ ] Confirm `dist/ims.exe` launches on a clean Windows installation.
- [ ] Verify `%APPDATA%/IMS` or the configured shared path is writable.
- [ ] Test Windows backup, migration, and restore behavior.

## Database Safety

- [ ] Create a backup before upgrading an existing database.
- [ ] Validate every release backup before distributing or restoring it.
- [ ] Keep at least one known-good backup outside the application directory.
- [ ] Do not place a shared SQLite database on storage without reliable file locking.
- [ ] Warn users that shared mode allows concurrent access but is not a substitute for a server database.

## Release Contents

- [ ] Application executable for the target operating system.
- [ ] `settings.ini` with a safe default configuration.
- [ ] `USER_GUIDE.md`.
- [ ] Backup and restore instructions.
- [ ] Version and release notes.
