"""GitHub CLI wrapper tools (Phase 1.3 stub).

Phase 1.4 で gh CLI を subprocess で呼ぶ wrapper を実装。
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def gh_issue_list(filter_str: str = "") -> list[dict]:
    """gh issue list の wrapper。filter_str は gh の --search に渡される。"""
    raise NotImplementedError("Phase 1.4 で実装")


@tool
def gh_issue_create(title: str, body: str, labels: list[str]) -> int:
    """Issue を作成し、issue number を返す。"""
    raise NotImplementedError("Phase 1.4 で実装")


@tool
def gh_issue_edit(
    num: int,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> None:
    """Issue のラベル遷移。"""
    raise NotImplementedError("Phase 1.4 で実装")


@tool
def gh_pr_create(branch: str, title: str, body: str) -> dict:
    """PR を作成し、{number, url} を返す。"""
    raise NotImplementedError("Phase 1.4 で実装")


@tool
def gh_pr_comments(pr: int) -> list[dict]:
    """PR のレビューコメントを取得。"""
    raise NotImplementedError("Phase 1.4 で実装")


@tool
def gh_pr_reply(pr: int, comment_id: int, body: str) -> None:
    """PR のレビューコメントに reply する。"""
    raise NotImplementedError("Phase 1.4 で実装")
