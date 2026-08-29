"""Unit tests for ``SessionDB.update_session_cwd_by_session_key``.

Gateway rows mint timestamped uuid ids while routing persists only the
``session_key``; this helper must resolve the key to the row that key
currently points at before the cwd write.
"""

from __future__ import annotations

from hermes_state import SessionDB


def _db(tmp_path):
    return SessionDB(db_path=tmp_path / "state.db")


def _row(db, session_id):
    return db.get_session(session_id)


def test_resolves_open_row_and_persists_cwd_and_git_meta(tmp_path):
    db = _db(tmp_path)
    db.create_session(
        "20260828_100000_abc12345",
        "telegram",
        session_key="agent:main:telegram:group:-100:user",
    )
    generation = db.update_session_cwd_by_session_key(
        "agent:main:telegram:group:-100:user",
        "/repo/alpha",
        git_branch="feature/x",
        git_repo_root="/repo/alpha",
    )
    assert isinstance(generation, int) and not isinstance(generation, bool)
    row = _row(db, "20260828_100000_abc12345")
    assert row["cwd"] == "/repo/alpha"
    assert row["git_branch"] == "feature/x"
    assert row["git_repo_root"] == "/repo/alpha"


def test_prefers_open_row_over_older_and_newer_closed_rows(tmp_path):
    db = _db(tmp_path)
    # Reset chain under one key: old row closed, open successor, and a
    # later-started but also-closed row (closed after the open one started).
    db.create_session("row_old", "telegram", session_key="agent:main:telegram:dm")
    db.end_session("row_old", "reset")
    db.create_session("row_open", "telegram", session_key="agent:main:telegram:dm")
    db.create_session("row_later_closed", "telegram", session_key="agent:main:telegram:dm")
    db.end_session("row_later_closed", "reset")

    assert db.update_session_cwd_by_session_key(
        "agent:main:telegram:dm", "/repo/live"
    ) is not None
    row = _row(db, "row_open")
    assert row["cwd"] == "/repo/live"
    # The closed rows are untouched.
    assert _row(db, "row_old")["cwd"] is None
    assert _row(db, "row_later_closed")["cwd"] is None


def test_falls_back_to_latest_closed_row_when_none_open(tmp_path):
    db = _db(tmp_path)
    db.create_session("row_first", "telegram", session_key="agent:main:discord:dm")
    db.end_session("row_first", "reset")
    db.create_session("row_second", "telegram", session_key="agent:main:discord:dm")
    db.end_session("row_second", "reset")

    assert db.update_session_cwd_by_session_key(
        "agent:main:discord:dm", "/repo/fallback"
    ) is not None
    assert _row(db, "row_second")["cwd"] == "/repo/fallback"
    assert _row(db, "row_first")["cwd"] is None


def test_unknown_key_returns_none_without_creating_a_row(tmp_path):
    db = _db(tmp_path)
    assert (
        db.update_session_cwd_by_session_key(
            "agent:main:slack:dm", "/repo/nowhere"
        )
        is None
    )
    with db._lock:
        count = db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 0


def test_empty_arguments_are_rejected(tmp_path):
    db = _db(tmp_path)
    assert db.update_session_cwd_by_session_key("", "/repo/x") is None
    db.create_session("row", "telegram", session_key="agent:main:telegram:dm")
    assert db.update_session_cwd_by_session_key("agent:main:telegram:dm", "") is None
