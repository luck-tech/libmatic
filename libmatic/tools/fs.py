"""File I/O tools (Read / Write / Edit)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


@tool
def read_file(path: str) -> str:
    """指定パスのファイルを UTF-8 で読み込んで内容を返す。"""
    return Path(path).read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """指定パスに UTF-8 でファイルを書き込む。既存なら上書き。親ディレクトリは自動作成。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


@tool
def edit_file(path: str, old: str, new: str) -> str:
    """ファイル内の old を new に置換。old が一意に存在しない場合エラー。"""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise ValueError(f"old string not found in {path}")
    if count > 1:
        raise ValueError(f"old string not unique in {path} (appears {count} times)")
    new_text = text.replace(old, new)
    p.write_text(new_text, encoding="utf-8")
    return f"Replaced 1 occurrence in {path}"
