"""Tests for libmatic.nodes.pr_review (C1-C5)."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from libmatic.config import GitHubConfig, LibmaticConfig
from libmatic.nodes.pr_review import (
    _build_reply_body,
    _coerce_review_comment,
    _has_staged_changes,
    _parse_classification_object,
    address_each,
    classify_comments,
    collect_comments,
    commit_push,
    reply_comments,
)
from libmatic.state.pr_review import PRReviewState, ReviewComment


def _make_config() -> LibmaticConfig:
    return LibmaticConfig(github=GitHubConfig(repo="OWNER/REPO"))


def _rc(lcfg: LibmaticConfig) -> RunnableConfig:
    return {"configurable": {"libmatic_config": lcfg}}


def _fake_agent_returning(content: str) -> Any:
    fake = MagicMock()
    fake.invoke = MagicMock(
        return_value={"messages": [MagicMock(content=content)]}
    )
    return fake


def _fake_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=""
    )


# --- _coerce_review_comment ---


def test_coerce_review_comment_from_gh_api_shape() -> None:
    raw = {
        "id": 100,
        "body": "fix typo",
        "path": "src/x.py",
        "line": 10,
        "user": {"login": "reviewer"},
    }
    c = _coerce_review_comment(raw)
    assert c is not None
    assert c.id == 100
    assert c.author == "reviewer"
    assert c.path == "src/x.py"


def test_coerce_review_comment_missing_required() -> None:
    assert _coerce_review_comment({"body": "x"}) is None  # no id
    assert _coerce_review_comment({"id": 1}) is None  # no body
    assert _coerce_review_comment("string") is None  # not dict


def test_coerce_review_comment_optional_path_line_null() -> None:
    raw = {"id": 1, "body": "general comment", "user": {"login": "r"}}
    c = _coerce_review_comment(raw)
    assert c is not None
    assert c.path is None
    assert c.line is None


# --- C1: collect_comments ---


def test_collect_comments_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    monkeypatch.setattr(
        nodes_mod, "gh_pr_comments_core",
        lambda pr: [
            {"id": 1, "body": "a", "user": {"login": "x"}, "path": "f.py", "line": 1},
            {"id": 2, "body": "b", "user": {"login": "y"}},
        ],
    )

    state = PRReviewState(pr_number=37)
    result = collect_comments(state, _rc(_make_config()))
    assert len(result["comments"]) == 2
    assert {c.id for c in result["comments"]} == {1, 2}


def test_collect_comments_gh_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import libmatic.nodes.pr_review as nodes_mod
    from libmatic.tools.github import GhError

    def raises(_: int) -> list[dict]:
        raise GhError("auth failed")

    monkeypatch.setattr(nodes_mod, "gh_pr_comments_core", raises)

    state = PRReviewState(pr_number=1)
    result = collect_comments(state, _rc(_make_config()))
    assert result == {"comments": []}


# --- _parse_classification_object ---


def test_parse_classification_object_valid() -> None:
    content = '{"123": "address", "124": "reply", "125": "ignore"}'
    out = _parse_classification_object(content)
    assert out == {123: "address", 124: "reply", 125: "ignore"}


def test_parse_classification_object_with_surrounding_text() -> None:
    content = '回答: {"1": "address"}\n以上'
    assert _parse_classification_object(content) == {1: "address"}


def test_parse_classification_object_invalid_class_dropped() -> None:
    content = '{"1": "address", "2": "unknown_class", "3": "reply"}'
    out = _parse_classification_object(content)
    assert out == {1: "address", 3: "reply"}


def test_parse_classification_object_non_int_key_dropped() -> None:
    content = '{"abc": "address", "1": "reply"}'
    assert _parse_classification_object(content) == {1: "reply"}


def test_parse_classification_object_invalid_json() -> None:
    assert _parse_classification_object("") == {}
    assert _parse_classification_object("not json") == {}
    assert _parse_classification_object("{broken") == {}


# --- C2: classify_comments ---


def test_classify_comments_parses_object(monkeypatch: pytest.MonkeyPatch) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    fake_output = '{"1": "address", "2": "reply"}'
    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning(fake_output),
    )

    comments = [
        ReviewComment(id=1, body="fix", author="r"),
        ReviewComment(id=2, body="?", author="r"),
        ReviewComment(id=3, body="LGTM", author="r"),
    ]
    state = PRReviewState(pr_number=37, comments=comments)
    result = classify_comments(state, _rc(_make_config()))

    assert result["classified"][1] == "address"
    assert result["classified"][2] == "reply"
    # LLM が言及しなかった id 3 は ignore で埋まる
    assert result["classified"][3] == "ignore"


def test_classify_comments_empty_comments_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    def should_not_be_called(*a: Any, **kw: Any) -> Any:
        raise AssertionError("agent should not be built when no comments")

    monkeypatch.setattr(nodes_mod, "build_step_agent", should_not_be_called)

    state = PRReviewState(pr_number=1, comments=[])
    result = classify_comments(state, _rc(_make_config()))
    assert result == {"classified": {}}


def test_classify_comments_llm_failure_falls_back_to_ignore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    class Failing:
        def invoke(self, _: dict) -> dict:
            raise RuntimeError("LLM down")

    monkeypatch.setattr(nodes_mod, "build_step_agent", lambda *a, **kw: Failing())

    state = PRReviewState(
        pr_number=1,
        comments=[ReviewComment(id=1, body="x", author="r")],
    )
    result = classify_comments(state, _rc(_make_config()))
    assert result["classified"] == {1: "ignore"}


# --- C3: address_each ---


def test_address_each_records_actions_log(monkeypatch: pytest.MonkeyPatch) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    fake_output = json.dumps(
        [
            {
                "comment_id": 100,
                "status": "addressed",
                "action_summary": "src/x.py L42 の typo を修正",
                "files_touched": ["src/x.py"],
            }
        ]
    )
    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning(fake_output),
    )

    state = PRReviewState(
        pr_number=37,
        comments=[ReviewComment(id=100, body="typo", author="r", path="src/x.py", line=42)],
        classified={100: "address"},
    )
    result = address_each(state, _rc(_make_config()))
    assert len(result["actions_log"]) == 1
    assert result["actions_log"][0]["comment_id"] == 100
    assert result["actions_log"][0]["status"] == "addressed"


def test_address_each_no_targets_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    def should_not_be_called(*a: Any, **kw: Any) -> Any:
        raise AssertionError("agent should not run when no address targets")

    monkeypatch.setattr(nodes_mod, "build_step_agent", should_not_be_called)

    # address 分類された comment が無い (全 reply / ignore)
    state = PRReviewState(
        pr_number=1,
        comments=[ReviewComment(id=1, body="?", author="r")],
        classified={1: "reply"},
    )
    result = address_each(state, _rc(_make_config()))
    assert result["actions_log"] == []


def test_address_each_deferred_demotes_to_ignore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM が status=deferred と返したら、その comment は classified を ignore に降格。"""
    import libmatic.nodes.pr_review as nodes_mod

    fake_output = json.dumps(
        [
            {
                "comment_id": 100,
                "status": "deferred",
                "action_summary": "判断保留、人間に委ねる",
                "files_touched": [],
            }
        ]
    )
    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning(fake_output),
    )

    state = PRReviewState(
        pr_number=1,
        comments=[ReviewComment(id=100, body="?", author="r")],
        classified={100: "address"},
    )
    result = address_each(state, _rc(_make_config()))
    assert result["classified"][100] == "ignore"


# --- _has_staged_changes ---


def test_has_staged_changes_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(["git"], 1, "", ""),
    )
    assert _has_staged_changes() is True


def test_has_staged_changes_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(["git"], 0, "", ""),
    )
    assert _has_staged_changes() is False


def test_has_staged_changes_no_git_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raises(*a: Any, **kw: Any) -> subprocess.CompletedProcess:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", raises)
    assert _has_staged_changes() is False


# --- C4: commit_push ---


def test_commit_push_no_actions_returns_uncommitted() -> None:
    state = PRReviewState(pr_number=1, actions_log=[])
    result = commit_push(state, _rc(_make_config()))
    assert result == {"committed": False}


def test_commit_push_no_addressed_returns_uncommitted() -> None:
    state = PRReviewState(
        pr_number=1,
        actions_log=[{"comment_id": 1, "status": "deferred", "files_touched": []}],
    )
    result = commit_push(state, _rc(_make_config()))
    assert result == {"committed": False}


def test_commit_push_runs_git_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """addressed entry あり → add / commit / push が呼ばれる。"""
    git_calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, check: bool = True, capture_output: bool = False, **kw: Any) -> Any:
        git_calls.append(cmd)
        if cmd[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(cmd, 1, "", "")  # 差分あり
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = PRReviewState(
        pr_number=37,
        actions_log=[
            {
                "comment_id": 100,
                "status": "addressed",
                "action_summary": "fix",
                "files_touched": ["src/x.py"],
            }
        ],
    )
    result = commit_push(state, _rc(_make_config()))
    assert result == {"committed": True}
    actions = [c[1] for c in git_calls if len(c) > 1]
    assert "add" in actions
    assert "commit" in actions
    assert "push" in actions


def test_commit_push_no_staged_changes_after_add(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """git add 後に diff --cached が 0 (差分なし) → commit せず False を返す。"""

    def fake_run(cmd: list[str], *, check: bool = True, capture_output: bool = False, **kw: Any) -> Any:
        if cmd[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")  # 差分なし
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = PRReviewState(
        pr_number=1,
        actions_log=[
            {
                "comment_id": 1,
                "status": "addressed",
                "action_summary": "x",
                "files_touched": ["a.py"],
            }
        ],
    )
    result = commit_push(state, _rc(_make_config()))
    assert result == {"committed": False}


def test_commit_push_git_failure_returns_uncommitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], *, check: bool = True, **kw: Any) -> Any:
        if cmd[1] == "add":
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = PRReviewState(
        pr_number=1,
        actions_log=[
            {"comment_id": 1, "status": "addressed", "files_touched": ["a.py"]}
        ],
    )
    result = commit_push(state, _rc(_make_config()))
    assert result == {"committed": False}


# --- _build_reply_body ---


def test_build_reply_body_address_with_summary() -> None:
    body = _build_reply_body(
        100,
        {"status": "addressed", "action_summary": "typo 修正", "files_touched": ["x.py"]},
        "address",
    )
    assert "対応しました" in body
    assert "typo 修正" in body
    assert "x.py" in body


def test_build_reply_body_reply_template() -> None:
    body = _build_reply_body(1, None, "reply")
    assert "確認済み" in body or "ありがとう" in body


def test_build_reply_body_deferred_explanation() -> None:
    body = _build_reply_body(
        1,
        {"status": "deferred"},
        "address",  # status=address だが log は deferred → 別途対応扱い
    )
    assert "別途" in body or "本 PR" in body


# --- C5: reply_comments ---


def test_reply_comments_replies_address_and_reply_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    replies: list[tuple[int, int, str]] = []

    def fake_reply(pr: int, cid: int, body: str) -> None:
        replies.append((pr, cid, body))

    monkeypatch.setattr(nodes_mod, "gh_pr_reply_core", fake_reply)

    state = PRReviewState(
        pr_number=37,
        comments=[
            ReviewComment(id=1, body="fix", author="r"),
            ReviewComment(id=2, body="?", author="r"),
            ReviewComment(id=3, body="LGTM", author="r"),
        ],
        classified={1: "address", 2: "reply", 3: "ignore"},
        actions_log=[
            {"comment_id": 1, "status": "addressed", "action_summary": "fix", "files_touched": []}
        ],
    )
    result = reply_comments(state, _rc(_make_config()))

    replied_ids = {r[1] for r in replies}
    assert replied_ids == {1, 2}  # ignore の 3 はスキップ
    assert sorted(result["replied_comment_ids"]) == [1, 2]


def test_reply_comments_skips_already_replied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.pr_review as nodes_mod

    replies: list[int] = []
    monkeypatch.setattr(
        nodes_mod, "gh_pr_reply_core",
        lambda pr, cid, body: replies.append(cid),
    )

    state = PRReviewState(
        pr_number=1,
        comments=[ReviewComment(id=1, body="x", author="r")],
        classified={1: "reply"},
        replied_comment_ids=[1],  # 既に reply 済み
    )
    result = reply_comments(state, _rc(_make_config()))
    assert replies == []
    assert result["replied_comment_ids"] == [1]


def test_reply_comments_gh_failure_skips_individual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """個別 reply 失敗は skip して残りを継続。"""
    import libmatic.nodes.pr_review as nodes_mod
    from libmatic.tools.github import GhError

    replied: list[int] = []

    def fake_reply(pr: int, cid: int, body: str) -> None:
        if cid == 1:
            raise GhError("403")
        replied.append(cid)

    monkeypatch.setattr(nodes_mod, "gh_pr_reply_core", fake_reply)

    state = PRReviewState(
        pr_number=1,
        comments=[
            ReviewComment(id=1, body="x", author="r"),
            ReviewComment(id=2, body="y", author="r"),
        ],
        classified={1: "reply", 2: "reply"},
    )
    result = reply_comments(state, _rc(_make_config()))
    assert replied == [2]
    assert result["replied_comment_ids"] == [2]
