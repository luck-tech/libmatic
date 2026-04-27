"""Tests for libmatic.checkpointer.sqlite."""

from __future__ import annotations

from pathlib import Path

import pytest

from libmatic.checkpointer import (
    build_thread_id,
    default_db_path,
    open_checkpointer,
)

# --- default_db_path ---


def test_default_db_path_under_home_libmatic() -> None:
    p = default_db_path()
    assert p.name == "state.sqlite"
    assert p.parent.name == ".libmatic"


# --- build_thread_id ---


def test_build_thread_id_format() -> None:
    tid = build_thread_id("topic-debate", 18, date="20260424")
    assert tid == "topic-debate-18-20260424"


def test_build_thread_id_with_string_key() -> None:
    tid = build_thread_id("address-pr-comments", "37", date="20260428")
    assert tid == "address-pr-comments-37-20260428"


def test_build_thread_id_default_date_is_today() -> None:
    from datetime import UTC, datetime

    tid = build_thread_id("x", 1)
    today = datetime.now(UTC).strftime("%Y%m%d")
    assert tid == f"x-1-{today}"


# --- open_checkpointer ---


def test_open_checkpointer_in_memory() -> None:
    """:memory: で開けて、context manager として動く。"""
    with open_checkpointer(":memory:") as saver:
        assert saver is not None
        # SqliteSaver は put / get_tuple を持つ
        assert hasattr(saver, "put")
        assert hasattr(saver, "get_tuple")


def test_open_checkpointer_creates_parent_dir(tmp_path: Path) -> None:
    """親ディレクトリが無くても自動作成される。"""
    target = tmp_path / "deep" / "nested" / "state.sqlite"
    assert not target.parent.exists()

    with open_checkpointer(target) as saver:
        assert saver is not None

    # parent dir が作られた (ファイル自体は put されるまで作られないかも)
    assert target.parent.exists()


def test_open_checkpointer_persists_to_file(tmp_path: Path) -> None:
    """to-disk で開くとファイルパス指定が反映される (ファイル作成は put 後)。"""
    db_file = tmp_path / "test.sqlite"
    with open_checkpointer(db_file) as saver:
        # checkpointer が valid に開けることを確認
        assert saver is not None


def test_open_checkpointer_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """db_path=None の場合 default_db_path() を使う。"""
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with open_checkpointer() as saver:
        assert saver is not None

    # ~/.libmatic ディレクトリが作られた
    assert (fake_home / ".libmatic").exists()
