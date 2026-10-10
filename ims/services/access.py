"""Password authentication and RBAC helpers used by the desktop UI."""

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class UserSession:
    """Authenticated user and the groups assigned to that user."""

    user_id: int
    username: str
    groups: tuple[str, ...]


def _password_hash(password: str, salt: bytes | None = None) -> str:
    """Hash a password with a per-user salt."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def _password_matches(password: str, stored_hash: str) -> bool:
    """Compare a password with a stored salt and PBKDF2 digest."""
    salt_hex, digest_hex = stored_hash.split("$", 1)
    expected = _password_hash(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
    return secrets.compare_digest(expected, digest_hex)


def list_groups(connection: sqlite3.Connection) -> list[str]:
    """Return available groups in display order."""
    rows = connection.execute("SELECT name FROM groups ORDER BY id").fetchall()
    return [row[0] for row in rows]


def has_permission(connection: sqlite3.Connection, group_name: str, permission: str) -> bool:
    """Return whether a group has a named permission."""
    return connection.execute(
        "SELECT 1 FROM groups g "
        "JOIN group_permissions gp ON gp.group_id = g.id "
        "JOIN permissions p ON p.id = gp.permission_id "
        "WHERE g.name = ? AND p.code = ?",
        (group_name, permission),
    ).fetchone() is not None


def session_has_permission(session: UserSession, connection: sqlite3.Connection, permission: str) -> bool:
    """Return whether any group assigned to the session has a permission."""
    return any(has_permission(connection, group, permission) for group in session.groups)


def create_user(
    connection: sqlite3.Connection, username: str, password: str, group_names: list[str]
) -> int:
    """Create a user with at least one existing group."""
    username = username.strip()
    if not username or len(password) < 8:
        raise ValueError("Username is required and password must contain at least 8 characters")
    if not group_names:
        raise ValueError("Assign at least one group")
    with connection:
        cursor = connection.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, _password_hash(password)),
        )
        for group_name in group_names:
            group = connection.execute("SELECT id FROM groups WHERE name = ?", (group_name,)).fetchone()
            if group is None:
                raise ValueError(f"Unknown group: {group_name}")
            connection.execute(
                "INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
                (cursor.lastrowid, group[0]),
            )
    if cursor.lastrowid is None:
        raise RuntimeError("User insert did not return an ID")
    return cursor.lastrowid


def authenticate(connection: sqlite3.Connection, username: str, password: str) -> UserSession:
    """Authenticate an active user and return its assigned groups."""
    row = connection.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ? AND active = 1",
        (username.strip(),),
    ).fetchone()
    if row is None or not row[2] or not _password_matches(password, row[2]):
        raise ValueError("Invalid username or password")
    groups = connection.execute(
        "SELECT g.name FROM groups g JOIN user_groups ug ON ug.group_id = g.id "
        "WHERE ug.user_id = ? ORDER BY g.id",
        (row[0],),
    ).fetchall()
    return UserSession(row[0], row[1], tuple(group[0] for group in groups))
