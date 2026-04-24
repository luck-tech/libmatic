"""Tests for libmatic.tools.github (Phase 1.4 PoC #4, gh CLI wrapper)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from libmatic.tools.github import (
    GhError,
    _parse_issue_number_from_url,
    gh_issue_create_core,
    gh_issue_edit_core,
    gh_issue_list_core,
    gh_pr_comments_core,
    gh_pr_create_core,
    gh_pr_reply_core,
)


def _fake_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=""
    )


# --- _parse_issue_number_from_url ---


def test_parse_issue_number_from_url() -> None:
    assert _parse_issue_number_from_url("https://github.com/owner/repo/issues/42") == 42


def test_parse_issue_number_from_url_trailing_slash() -> None:
    assert _parse_issue_number_from_url("https://github.com/o/r/issues/123/") == 123


def test_parse_issue_number_invalid_raises() -> None:
    with pytest.raises(GhError):
        _parse_issue_number_from_url("https://github.com/o/r/issues/not-a-number")


# --- gh_issue_list_core ---


def test_gh_issue_list_core_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed(json.dumps([{"number": 1, "title": "t"}]))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = gh_issue_list_core(labels=["topic/ready"], state="open", limit=10)
    assert result == [{"number": 1, "title": "t"}]
    # gh issue list ... --label topic/ready が正しく構築されている
    cmd = captured["cmd"]
    assert cmd[0] == "gh"
    assert "issue" in cmd and "list" in cmd
    assert "--label" in cmd
    assert "topic/ready" in cmd
    assert "--state" in cmd and "open" in cmd
    assert "10" in cmd


def test_gh_issue_list_core_multiple_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed("[]")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_issue_list_core(labels=["a", "b"])
    cmd = captured["cmd"]
    # 各 label が --label で渡される
    assert cmd.count("--label") == 2
    assert "a" in cmd and "b" in cmd


def test_gh_issue_list_core_with_search(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed("[]")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_issue_list_core(search="react compiler")
    cmd = captured["cmd"]
    assert "--search" in cmd
    assert "react compiler" in cmd


def test_gh_issue_list_core_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_completed(""))
    assert gh_issue_list_core() == []


def test_gh_issue_list_core_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_completed("not-json{"))
    with pytest.raises(GhError):
        gh_issue_list_core()


# --- gh_issue_create_core ---


def test_gh_issue_create_core_returns_number(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return _fake_completed("https://github.com/owner/repo/issues/77\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert gh_issue_create_core("title", "body", labels=["topic/pending"]) == 77


def test_gh_issue_create_core_passes_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed("https://github.com/x/y/issues/1")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_issue_create_core("t", "b", labels=["lbl1", "lbl2"])
    cmd = captured["cmd"]
    assert cmd[0:3] == ["gh", "issue", "create"]
    assert cmd.count("--label") == 2


def test_gh_issue_create_core_weird_output_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return _fake_completed("some unexpected output")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GhError):
        gh_issue_create_core("t", "b")


# --- gh_issue_edit_core ---


def test_gh_issue_edit_core_label_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_issue_edit_core(
        22, add_labels=["topic/in-progress"], remove_labels=["topic/ready"]
    )
    cmd = captured["cmd"]
    assert cmd[0:3] == ["gh", "issue", "edit"]
    assert "22" in cmd
    assert "--add-label" in cmd and "topic/in-progress" in cmd
    assert "--remove-label" in cmd and "topic/ready" in cmd


def test_gh_issue_edit_core_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_issue_edit_core(1, body="新しい body")
    cmd = captured["cmd"]
    assert "--body" in cmd
    assert "新しい body" in cmd


# --- gh_pr_create_core ---


def test_gh_pr_create_core_returns_number_and_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return _fake_completed("https://github.com/owner/repo/pull/99\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = gh_pr_create_core(branch="topic/x", title="t", body="b")
    assert result["number"] == 99
    assert result["url"] == "https://github.com/owner/repo/pull/99"


def test_gh_pr_create_core_passes_head_and_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed("https://github.com/x/y/pull/1")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_pr_create_core(branch="feat/x", title="t", body="b", base="develop")
    cmd = captured["cmd"]
    assert cmd[0:3] == ["gh", "pr", "create"]
    idx_head = cmd.index("--head")
    idx_base = cmd.index("--base")
    assert cmd[idx_head + 1] == "feat/x"
    assert cmd[idx_base + 1] == "develop"


# --- gh_pr_comments_core ---


def test_gh_pr_comments_core_success(monkeypatch: pytest.MonkeyPatch) -> None:
    comments = [
        {"id": 1, "body": "nit", "user": {"login": "reviewer"}},
        {"id": 2, "body": "LGTM", "user": {"login": "other"}},
    ]

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        cmd = args[0]
        assert "api" in cmd
        assert "--paginate" in cmd
        return _fake_completed(json.dumps(comments))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = gh_pr_comments_core(37)
    assert result == comments


def test_gh_pr_comments_core_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_completed("oops"))
    with pytest.raises(GhError):
        gh_pr_comments_core(1)


# --- gh_pr_reply_core ---


def test_gh_pr_reply_core_posts_with_method(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    gh_pr_reply_core(pr=37, comment_id=12345, body="修正しました")
    cmd = captured["cmd"]
    assert "api" in cmd
    assert "--method" in cmd
    i = cmd.index("--method")
    assert cmd[i + 1] == "POST"
    # body は -f body=... で渡される
    assert "-f" in cmd
    assert any("body=修正しました" in x for x in cmd)


# --- error handling ---


def test_run_gh_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GhError) as exc:
        gh_issue_list_core()
    assert "見つかりません" in str(exc.value)


def test_run_gh_called_process_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.CalledProcessError(
            1, ["gh"], output="", stderr="auth failed"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GhError) as exc:
        gh_issue_list_core()
    assert "失敗" in str(exc.value)
    assert "auth failed" in str(exc.value)


def test_run_gh_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(["gh"], 60)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GhError) as exc:
        gh_issue_list_core()
    assert "timeout" in str(exc.value)


# --- @tool wrapper (invoke) ---


def test_gh_issue_list_tool_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from libmatic.tools.github import gh_issue_list

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: _fake_completed('[{"number": 1}]')
    )
    result = gh_issue_list.invoke({"labels": ["x"], "state": "open"})
    assert result == [{"number": 1}]


def test_gh_issue_create_tool_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from libmatic.tools.github import gh_issue_create

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _fake_completed("https://github.com/x/y/issues/100\n"),
    )
    result = gh_issue_create.invoke({"title": "t", "body": "b"})
    assert result == 100
