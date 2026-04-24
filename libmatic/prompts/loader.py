"""Prompt loader.

libmatic/prompts/*.md を読み、`{{PHILOSOPHY}}` を philosophy.md の内容で置換する。
各 step の system prompt はこの loader 経由で取得。
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
PHILOSOPHY_PLACEHOLDER = "{{PHILOSOPHY}}"


@cache
def _read_prompt_file(rel_path: str) -> str:
    path = PROMPTS_DIR / rel_path
    if not path.exists():
        raise FileNotFoundError(f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_prompt(rel_path: str) -> str:
    """Prompt md を読み、{{PHILOSOPHY}} を philosophy.md で置換して返す。

    Args:
        rel_path: prompts/ 配下の相対 path (例: 'topic_debate/step6_coverage_verifier.md')

    Raises:
        FileNotFoundError: 指定の md が存在しない場合
    """
    raw = _read_prompt_file(rel_path)
    if PHILOSOPHY_PLACEHOLDER in raw:
        philosophy = _read_prompt_file("philosophy.md")
        raw = raw.replace(PHILOSOPHY_PLACEHOLDER, philosophy)
    return raw


def clear_prompt_cache() -> None:
    """test や開発時に prompt を再読み込みしたいときに呼ぶ."""
    _read_prompt_file.cache_clear()
