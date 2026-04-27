"""Tests for libmatic.scaffold."""

from __future__ import annotations

from pathlib import Path

import pytest

from libmatic.scaffold import (
    DEFAULT_CATEGORIES,
    PRESET_CHOICES,
    TEMPLATES_DIR,
    InitOptions,
    render_libmatic_yml,
    write_scaffold,
)


def _opts(target: Path, **overrides: object) -> InitOptions:
    base: dict[str, object] = {
        "target_dir": target,
        "github_repo": "luck-tech/my_library",
        "preset": "balanced",
    }
    base.update(overrides)
    return InitOptions(**base)  # type: ignore[arg-type]


# --- defaults ---


def test_preset_choices_match_factory() -> None:
    from libmatic.providers.factory import PRESET_MODELS

    assert set(PRESET_CHOICES) == set(PRESET_MODELS["anthropic"].keys())


def test_default_categories_match_libmatic_config_default() -> None:
    from libmatic.config import GitHubConfig, LibmaticConfig

    cfg = LibmaticConfig(github=GitHubConfig(repo="x/y"))
    assert tuple(DEFAULT_CATEGORIES) == tuple(cfg.content.categories)


def test_templates_dir_has_required_files() -> None:
    assert TEMPLATES_DIR.is_dir()
    required = [
        "config/libmatic.yml",
        "config/source_priorities.yml",
        ".env.example",
        ".gitignore.template",
        ".github/workflows/weekly-suggest.yml",
        ".github/workflows/nightly-debate.yml",
        ".github/ISSUE_TEMPLATE/topic.yml",
        ".claude/commands/suggest-topics.md",
        ".claude/commands/topic-debate.md",
        ".claude/commands/address-pr-comments.md",
        "scripts/launchd/com.libmatic.suggest-topics.weekly.plist.example",
        "scripts/launchd/com.libmatic.topic-debate.nightly.plist.example",
    ]
    for rel in required:
        assert (TEMPLATES_DIR / rel).exists(), f"missing template: {rel}"


# --- InitOptions ---


def test_init_options_invalid_preset(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _opts(tmp_path, preset="ultra")


def test_init_options_empty_categories(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _opts(tmp_path, categories=())


# --- render_libmatic_yml ---


def test_render_substitutes_preset_and_repo(tmp_path: Path) -> None:
    opts = _opts(tmp_path, preset="quality", github_repo="acme/foo")
    out = render_libmatic_yml(opts)
    assert "preset: quality" in out
    assert "repo: acme/foo" in out
    assert "{{PRESET}}" not in out
    assert "{{CATEGORIES_YAML}}" not in out
    assert "{{GITHUB_REPO}}" not in out


def test_render_categories_yaml_indented(tmp_path: Path) -> None:
    opts = _opts(tmp_path, categories=("alpha", "beta"))
    out = render_libmatic_yml(opts)
    assert "    - alpha" in out
    assert "    - beta" in out


# --- write_scaffold ---


def test_write_scaffold_full_default(tmp_path: Path) -> None:
    opts = write_scaffold(_opts(tmp_path))

    # 必須ファイル
    assert (tmp_path / "config" / "libmatic.yml").exists()
    assert (tmp_path / "config" / "source_priorities.yml").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".gitignore").exists()
    # GH Actions (default ON)
    assert (tmp_path / ".github" / "workflows" / "weekly-suggest.yml").exists()
    assert (tmp_path / ".github" / "workflows" / "nightly-debate.yml").exists()
    assert (tmp_path / ".github" / "ISSUE_TEMPLATE" / "topic.yml").exists()
    # Claude Code (default ON)
    assert (tmp_path / ".claude" / "commands" / "suggest-topics.md").exists()
    # launchd (default OFF) なし
    assert not (tmp_path / "scripts" / "launchd").exists()
    # content/categories
    for cat in DEFAULT_CATEGORIES:
        assert (tmp_path / "content" / cat / "notes" / ".gitkeep").exists()
    assert (tmp_path / "content" / "digest" / ".gitkeep").exists()

    assert len(opts.written_files) > 10


def test_write_scaffold_libmatic_yml_substitutes(tmp_path: Path) -> None:
    write_scaffold(_opts(tmp_path, preset="economy", github_repo="alice/repo"))
    yml = (tmp_path / "config" / "libmatic.yml").read_text(encoding="utf-8")
    assert "preset: economy" in yml
    assert "repo: alice/repo" in yml
    assert "{{" not in yml


def test_write_scaffold_skips_claude_when_disabled(tmp_path: Path) -> None:
    write_scaffold(_opts(tmp_path, include_claude_code=False))
    assert not (tmp_path / ".claude").exists()


def test_write_scaffold_skips_github_actions_when_disabled(tmp_path: Path) -> None:
    write_scaffold(_opts(tmp_path, include_github_actions=False))
    assert not (tmp_path / ".github").exists()


def test_write_scaffold_includes_launchd_when_enabled(tmp_path: Path) -> None:
    write_scaffold(_opts(tmp_path, include_launchd=True))
    assert (
        tmp_path / "scripts" / "launchd"
        / "com.libmatic.suggest-topics.weekly.plist.example"
    ).exists()
    assert (
        tmp_path / "scripts" / "launchd"
        / "com.libmatic.topic-debate.nightly.plist.example"
    ).exists()


def test_write_scaffold_does_not_overwrite_existing(tmp_path: Path) -> None:
    """既存ファイルがあれば overwrite=False で skip される。"""
    existing = tmp_path / "config" / "libmatic.yml"
    existing.parent.mkdir(parents=True)
    existing.write_text("# pre-existing user content\n", encoding="utf-8")

    opts = write_scaffold(_opts(tmp_path, overwrite=False))
    # 上書きされない
    assert existing.read_text(encoding="utf-8") == "# pre-existing user content\n"
    # 既存以外は書かれているので written_files は 1+
    assert existing not in opts.written_files


def test_write_scaffold_overwrite_true_replaces(tmp_path: Path) -> None:
    existing = tmp_path / "config" / "libmatic.yml"
    existing.parent.mkdir(parents=True)
    existing.write_text("# old\n", encoding="utf-8")

    write_scaffold(_opts(tmp_path, overwrite=True))
    assert "preset:" in existing.read_text(encoding="utf-8")


def test_write_scaffold_categories_create_notes_dirs(tmp_path: Path) -> None:
    write_scaffold(_opts(tmp_path, categories=("custom-cat-1", "custom-cat-2")))
    assert (tmp_path / "content" / "custom-cat-1" / "notes" / ".gitkeep").exists()
    assert (tmp_path / "content" / "custom-cat-2" / "notes" / ".gitkeep").exists()
