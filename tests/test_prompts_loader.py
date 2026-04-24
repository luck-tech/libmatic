"""Tests for libmatic.prompts.loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from libmatic.prompts.loader import (
    PHILOSOPHY_PLACEHOLDER,
    PROMPTS_DIR,
    clear_prompt_cache,
    load_prompt,
)


def setup_function() -> None:
    """各 test 前に cache を飛ばす (ファイルが変わったときに反映するため)."""
    clear_prompt_cache()


def test_prompts_dir_is_package_dir() -> None:
    assert PROMPTS_DIR.is_dir()
    assert (PROMPTS_DIR / "philosophy.md").exists()


def test_load_philosophy_returns_text() -> None:
    text = load_prompt("philosophy.md")
    assert text.strip() != ""
    # lifespan / 昇華 / universal などの用語が含まれる
    assert "lifespan" in text.lower() or "universal" in text.lower()


def test_load_step6_substitutes_philosophy_placeholder() -> None:
    text = load_prompt("topic_debate/step6_coverage_verifier.md")
    # placeholder は消えていて、philosophy の本文が含まれる
    assert PHILOSOPHY_PLACEHOLDER not in text
    # philosophy.md に含まれる語を確認
    phil = load_prompt("philosophy.md")
    first_line = next((line for line in phil.splitlines() if line.strip()), "")
    assert first_line.strip() in text


def test_load_prompt_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("topic_debate/definitely_not_exist.md")


def test_load_prompt_without_placeholder_returns_as_is(tmp_path: Path) -> None:
    """placeholder を含まない md は philosophy を読みに行かない。"""
    # philosophy 非依存ファイルとして philosophy.md 自体を使う
    text = load_prompt("philosophy.md")
    # philosophy.md には {{PHILOSOPHY}} 自体は含まれていない (自己 include は意味を持たない)
    assert PHILOSOPHY_PLACEHOLDER not in text
