"""Tests for libmatic.cli."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from libmatic.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    yml = tmp_path / "libmatic.yml"
    yml.write_text(
        """
version: 1
provider: anthropic
preset: balanced
github:
  repo: luck-tech/my_library
""",
        encoding="utf-8",
    )
    return yml


# --- version ---


def test_version_command(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    # __version__ が出力に含まれる
    assert "0." in result.stdout


# --- init (stub) ---


def test_init_help_lists_options(runner: CliRunner) -> None:
    """init は help で必要な options を documented する (実装は test_cli_init.py)."""
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "--target-dir" in result.stdout
    assert "--repo" in result.stdout
    assert "--preset" in result.stdout


# --- _load_config / _runtime_config ---


def test_load_config_missing_file(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        ["topic-debate", "1", "--config", "/tmp/does-not-exist-libmatic.yml",
         "--title", "T", "--body", "B"],
    )
    assert result.exit_code == 1
    assert "見つかりません" in (result.stderr or "")


def test_load_config_invalid_yaml(
    runner: CliRunner, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("not: [valid yaml: oops", encoding="utf-8")
    result = runner.invoke(
        app,
        ["topic-debate", "1", "--config", str(bad), "--title", "T", "--body", "B"],
    )
    assert result.exit_code == 1


# --- topic-debate ---


def test_topic_debate_invokes_graph(
    runner: CliRunner,
    sample_config_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """topic-debate サブコマンドが graph.invoke を正しい state で呼ぶ。"""

    captured: dict[str, Any] = {}

    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {
        "pr_number": 42,
        "pr_url": "https://github.com/x/y/pull/42",
    }
    fake_compiled = MagicMock()
    fake_compiled.compile.return_value = fake_graph

    def fake_build_graph() -> MagicMock:
        captured["builder_called"] = True
        return fake_compiled

    class FakeSaver:
        def __enter__(self) -> str:
            return "fake-saver"

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(
        "libmatic.workflows.topic_debate.build_topic_debate_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        "libmatic.checkpointer.open_checkpointer",
        lambda *a, **kw: FakeSaver(),
    )

    result = runner.invoke(
        app,
        [
            "topic-debate",
            "18",
            "--config",
            str(sample_config_yaml),
            "--title",
            "Test theme",
            "--body",
            "body",
            "--lifespan",
            "universal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("builder_called")
    # invoke の state 引数で issue_number=18 が渡る
    state_arg = fake_graph.invoke.call_args.args[0]
    assert state_arg.issue_number == 18
    assert state_arg.issue_title == "Test theme"
    # PR URL が stderr に出力
    assert "PR 作成" in (result.stderr or "")


def test_topic_debate_invalid_lifespan(
    runner: CliRunner, sample_config_yaml: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "topic-debate", "1",
            "--config", str(sample_config_yaml),
            "--title", "T", "--body", "B",
            "--lifespan", "invalid",
        ],
    )
    assert result.exit_code == 1


# --- suggest-topics ---


def test_suggest_topics_invokes_graph(
    runner: CliRunner,
    sample_config_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {
        "created_issues": [101, 102],
        "new_sources_detected": [],
    }
    fake_compiled = MagicMock()
    fake_compiled.compile.return_value = fake_graph

    monkeypatch.setattr(
        "libmatic.workflows.suggest_topics.build_suggest_topics_graph",
        lambda: fake_compiled,
    )

    class FakeSaver:
        def __enter__(self) -> str:
            return "saver"

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(
        "libmatic.checkpointer.open_checkpointer", lambda *a, **kw: FakeSaver()
    )

    result = runner.invoke(
        app, ["suggest-topics", "--config", str(sample_config_yaml)]
    )
    assert result.exit_code == 0, result.output
    assert "起票 2 件" in (result.stderr or "")


# --- address-pr-comments ---


def test_address_pr_comments_invokes_graph(
    runner: CliRunner,
    sample_config_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {
        "committed": True,
        "replied_comment_ids": [1, 2, 3],
    }
    fake_compiled = MagicMock()
    fake_compiled.compile.return_value = fake_graph

    monkeypatch.setattr(
        "libmatic.workflows.pr_review.build_pr_review_graph",
        lambda: fake_compiled,
    )

    class FakeSaver:
        def __enter__(self) -> str:
            return "s"

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(
        "libmatic.checkpointer.open_checkpointer", lambda *a, **kw: FakeSaver()
    )

    result = runner.invoke(
        app,
        ["address-pr-comments", "37", "--config", str(sample_config_yaml)],
    )
    assert result.exit_code == 0, result.output
    assert "commit=yes" in (result.stderr or "")
    assert "replies=3" in (result.stderr or "")


# --- resume ---


def test_resume_routes_topic_debate(
    runner: CliRunner,
    sample_config_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {"pr_url": "x"}
    fake_compiled = MagicMock()
    fake_compiled.compile.return_value = fake_graph

    captured: dict[str, bool] = {"td": False, "st": False, "pr": False}

    def fake_td() -> MagicMock:
        captured["td"] = True
        return fake_compiled

    monkeypatch.setattr(
        "libmatic.workflows.topic_debate.build_topic_debate_graph", fake_td
    )
    monkeypatch.setattr(
        "libmatic.workflows.suggest_topics.build_suggest_topics_graph",
        lambda: (_ for _ in ()).throw(AssertionError("st should not be called")),
    )

    class FakeSaver:
        def __enter__(self) -> str:
            return "s"

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(
        "libmatic.checkpointer.open_checkpointer", lambda *a, **kw: FakeSaver()
    )

    result = runner.invoke(
        app,
        ["resume", "topic-debate-18-20260424", "--config", str(sample_config_yaml)],
    )
    assert result.exit_code == 0, result.output
    assert captured["td"]


def test_resume_unknown_thread_id_prefix(
    runner: CliRunner, sample_config_yaml: Path
) -> None:
    result = runner.invoke(
        app,
        ["resume", "unknown-prefix-1", "--config", str(sample_config_yaml)],
    )
    assert result.exit_code == 1
    assert "判別できません" in (result.stderr or "")


# --- graph ---


def test_graph_outputs_mermaid(runner: CliRunner) -> None:
    result = runner.invoke(app, ["graph", "topic-debate"])
    assert result.exit_code == 0, result.output
    # mermaid 出力には graph 構文が入る
    out = result.stdout
    assert ("graph" in out.lower()) or ("flowchart" in out.lower())


def test_graph_unknown_workflow(runner: CliRunner) -> None:
    result = runner.invoke(app, ["graph", "does-not-exist"])
    assert result.exit_code == 1
    assert "未知の workflow" in (result.stderr or "")
