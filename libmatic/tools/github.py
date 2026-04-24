"""GitHub CLI (`gh`) wrapper tools.

libmatic 側の subprocess wrapper。gh CLI が install されていることを前提とし、
その上に薄く JSON / 戻り値の解釈を被せる。

v0.1 で必要な 6 つを実装:
- gh_issue_list:   issue 一覧取得
- gh_issue_create: issue 作成 → issue number を返す
- gh_issue_edit:   ラベル遷移 / body 更新
- gh_pr_create:    PR 作成 → {number, url}
- gh_pr_comments:  PR の review comments 取得
- gh_pr_reply:     review comment への reply
"""

from __future__ import annotations

import json
import subprocess

from langchain_core.tools import tool

DEFAULT_TIMEOUT = 60


class GhError(RuntimeError):
    """gh CLI 実行中のエラー (not found / exit code / timeout / parse 失敗)."""


def _run_gh(args: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """gh CLI を呼び出す汎用関数。失敗時は GhError を投げる。"""
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise GhError(
            "gh CLI が見つかりません (brew install gh などで install 要)"
        ) from e
    except subprocess.CalledProcessError as e:
        raise GhError(f"gh {' '.join(args)} 失敗: {e.stderr.strip()}") from e
    except subprocess.TimeoutExpired as e:
        raise GhError(f"gh {' '.join(args)} timeout ({timeout}s)") from e
    return result


def _parse_issue_number_from_url(url: str) -> int:
    """'https://github.com/owner/repo/issues/42' → 42。失敗時 GhError。"""
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except (ValueError, IndexError) as e:
        raise GhError(f"URL から issue/PR number を抽出できません: {url}") from e


# --- pure core functions (test しやすいように分離) ---


def gh_issue_list_core(
    labels: list[str] | None = None,
    state: str = "open",
    limit: int = 50,
    search: str | None = None,
) -> list[dict]:
    """`gh issue list` を JSON で呼んでパースする."""
    args: list[str] = [
        "issue",
        "list",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,labels,state,createdAt,body",
    ]
    for lb in labels or []:
        args += ["--label", lb]
    if search:
        args += ["--search", search]
    result = _run_gh(args)
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError as e:
        raise GhError(f"gh issue list の JSON parse 失敗: {e}") from e


def gh_issue_create_core(
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> int:
    """`gh issue create` → 出力 URL から issue number 抽出."""
    args: list[str] = ["issue", "create", "--title", title, "--body", body]
    for lb in labels or []:
        args += ["--label", lb]
    result = _run_gh(args)
    return _parse_issue_number_from_url(result.stdout.strip())


def gh_issue_edit_core(
    num: int,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    body: str | None = None,
) -> None:
    """`gh issue edit` でラベル遷移 / body 更新."""
    args: list[str] = ["issue", "edit", str(num)]
    for lb in add_labels or []:
        args += ["--add-label", lb]
    for lb in remove_labels or []:
        args += ["--remove-label", lb]
    if body is not None:
        args += ["--body", body]
    _run_gh(args)


def gh_pr_create_core(
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict:
    """`gh pr create` → {number, url}."""
    args: list[str] = [
        "pr",
        "create",
        "--head",
        branch,
        "--base",
        base,
        "--title",
        title,
        "--body",
        body,
    ]
    result = _run_gh(args)
    url = result.stdout.strip()
    return {"number": _parse_issue_number_from_url(url), "url": url}


def gh_pr_comments_core(pr: int) -> list[dict]:
    """PR の line-specific review comments を取得 (`gh api` を paginate で)."""
    result = _run_gh(
        [
            "api",
            f"repos/{{owner}}/{{repo}}/pulls/{pr}/comments",
            "--paginate",
        ]
    )
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError as e:
        raise GhError(f"gh pr comments の JSON parse 失敗: {e}") from e


def gh_pr_reply_core(pr: int, comment_id: int, body: str) -> None:
    """PR の review comment に reply (`gh api` POST)."""
    _run_gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{{owner}}/{{repo}}/pulls/{pr}/comments/{comment_id}/replies",
            "-f",
            f"body={body}",
        ]
    )


# --- LangChain @tool wrappers ---


@tool
def gh_issue_list(
    labels: list[str] | None = None,
    state: str = "open",
    limit: int = 50,
    search: str | None = None,
) -> list[dict]:
    """GitHub issue 一覧を取得する (`gh issue list` ラッパー)。

    Args:
        labels: フィルタするラベル (複数可)
        state: "open" / "closed" / "all"
        limit: 取得上限 (default 50)
        search: gh の --search 相当

    Returns:
        各 issue の dict のリスト。{number, title, labels, state, createdAt, body}
    """
    return gh_issue_list_core(labels, state, limit, search)


@tool
def gh_issue_create(
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> int:
    """GitHub issue を作成し、issue number を返す。"""
    return gh_issue_create_core(title, body, labels)


@tool
def gh_issue_edit(
    num: int,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    body: str | None = None,
) -> str:
    """Issue の label 遷移や body 更新を行う。戻り値は確認用の文字列。"""
    gh_issue_edit_core(num, add_labels, remove_labels, body)
    return f"edited issue #{num}"


@tool
def gh_pr_create(
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict:
    """PR を作成し、{number, url} を返す。"""
    return gh_pr_create_core(branch, title, body, base)


@tool
def gh_pr_comments(pr: int) -> list[dict]:
    """PR のレビューコメント (line-specific) を取得する。"""
    return gh_pr_comments_core(pr)


@tool
def gh_pr_reply(pr: int, comment_id: int, body: str) -> str:
    """PR のレビューコメントに reply を付ける。"""
    gh_pr_reply_core(pr, comment_id, body)
    return f"replied to comment {comment_id} on PR #{pr}"
