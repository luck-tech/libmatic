"""Tests for libmatic.cli init command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from libmatic.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_init_with_yes_uses_defaults(runner: CliRunner, tmp_path: Path) -> None:
    """--yes + 必要な引数指定で対話なしに scaffold が走る。"""
    result = runner.invoke(
        app,
        [
            "init",
            "--target-dir", str(tmp_path),
            "--repo", "acme/foo",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "config" / "libmatic.yml").exists()
    assert (tmp_path / ".env.example").exists()


def test_init_yes_without_repo_fails(runner: CliRunner, tmp_path: Path) -> None:
    """--yes だけで repo 省略すると exit 1。"""
    result = runner.invoke(
        app,
        ["init", "--target-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 1
    assert "--repo" in (result.stderr or "")


def test_init_invalid_repo_format(runner: CliRunner, tmp_path: Path) -> None:
    """owner/name 形式でない repo は弾く。"""
    result = runner.invoke(
        app,
        [
            "init", "--target-dir", str(tmp_path),
            "--repo", "no-slash-here", "--yes",
        ],
    )
    assert result.exit_code == 1


def test_init_invalid_preset(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "init", "--target-dir", str(tmp_path),
            "--repo", "x/y", "--preset", "ultra", "--yes",
        ],
    )
    assert result.exit_code == 1


def test_init_no_claude_skips_dir(runner: CliRunner, tmp_path: Path) -> None:
    runner.invoke(
        app,
        [
            "init", "--target-dir", str(tmp_path),
            "--repo", "x/y", "--yes", "--no-claude-code",
        ],
    )
    assert not (tmp_path / ".claude").exists()


def test_init_launchd_includes_plists(runner: CliRunner, tmp_path: Path) -> None:
    runner.invoke(
        app,
        [
            "init", "--target-dir", str(tmp_path),
            "--repo", "x/y", "--yes", "--launchd",
        ],
    )
    assert (
        tmp_path / "scripts" / "launchd"
        / "com.libmatic.suggest-topics.weekly.plist.example"
    ).exists()


def test_init_writes_libmatic_yml_with_repo(
    runner: CliRunner, tmp_path: Path
) -> None:
    runner.invoke(
        app,
        [
            "init", "--target-dir", str(tmp_path),
            "--repo", "alice/example", "--preset", "quality", "--yes",
        ],
    )
    yml = (tmp_path / "config" / "libmatic.yml").read_text(encoding="utf-8")
    assert "repo: alice/example" in yml
    assert "preset: quality" in yml
