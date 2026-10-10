"""Tests for password authentication and user-to-group assignments."""

import sqlite3

import pytest

from ims.database.connection import connect
from ims.services.access import authenticate, create_user, session_has_permission


def test_user_authentication_uses_assigned_group_permissions() -> None:
    """A logged-in user's permissions come from its stored group assignment."""
    connection = connect(":memory:")
    create_user(connection, "alice", "correct horse", ["Manager"])

    session = authenticate(connection, "alice", "correct horse")

    assert session.groups == ("Manager",)
    assert session_has_permission(session, connection, "stock.write")
    assert not session_has_permission(session, connection, "schema.create")


def test_authentication_rejects_wrong_password() -> None:
    """A wrong password cannot create a session."""
    connection = connect(":memory:")
    create_user(connection, "alice", "correct horse", ["Viewer"])

    with pytest.raises(ValueError, match="Invalid username or password"):
        authenticate(connection, "alice", "wrong password")


def test_duplicate_usernames_are_rejected() -> None:
    """Usernames remain unique at the database boundary."""
    connection = connect(":memory:")
    create_user(connection, "alice", "correct horse", ["Viewer"])

    with pytest.raises(sqlite3.IntegrityError):
        create_user(connection, "alice", "another password", ["Viewer"])
