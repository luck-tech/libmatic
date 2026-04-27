"""Node implementations for address-pr-comments workflow.

実装方針:
- C1 collect_comments (deterministic): gh_pr_comments_core で line-specific comments 取得
- C2 classify_comments (ReAct): 各 comment を address / reply / ignore に分類 (cheap tier)
- C3 address_each (ReAct loop): address 対象を edit_file 等で修正 (default tier)
- C4 commit_push (deterministic): git add / commit / push
- C5 reply_comments (deterministic): gh_pr_reply_core で reply
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from libmatic.agents.react import build_step_agent
from libmatic.nodes._helpers import (
    get_libmatic_config as _get_libmatic_config,
)
from libmatic.nodes._helpers import (
    last_message_content as _last_message_content,
)
from libmatic.nodes._helpers import (
    parse_json_array as _parse_json_array,
)
from libmatic.prompts.loader import load_prompt
from libmatic.state.pr_review import PRReviewState, ReviewComment
from libmatic.tools.bash import bash
from libmatic.tools.fs import edit_file, read_file, write_file
from libmatic.tools.github import (
    GhError,
    gh_pr_comments_core,
    gh_pr_reply_core,
)

# --- C1: collect_comments (deterministic) ---


def _coerce_review_comment(raw: Any) -> ReviewComment | None:
    """gh api JSON から ReviewComment dataclass を作る。失敗時 None。"""
    if not isinstance(raw, dict):
        return None
    rid = raw.get("id")
    body = raw.get("body")
    if rid is None or body is None:
        return None
    user = raw.get("user") or {}
    author = (
        user.get("login")
        if isinstance(user, dict)
        else str(raw.get("author") or "")
    )
    try:
        return ReviewComment(
            id=int(rid),
            body=str(body),
            path=raw.get("path"),
            line=raw.get("line"),
            author=str(author or ""),
        )
    except Exception:
        return None


def collect_comments(state: PRReviewState, config: RunnableConfig) -> dict:
    """C1: PR の line-specific review comments を gh api で取得。"""
    _get_libmatic_config(config)
    try:
        raw_comments = gh_pr_comments_core(state.pr_number)
    except GhError:
        return {"comments": []}

    comments: list[ReviewComment] = []
    for r in raw_comments:
        c = _coerce_review_comment(r)
        if c is not None:
            comments.append(c)
    return {"comments": comments}


# --- C2: classify_comments (ReAct, cheap tier) ---


def _parse_classification_object(content: str) -> dict[int, str]:
    """LLM 出力から `{<id>: <class>}` を抽出。invalid なら空 dict。"""
    if not content:
        return {}
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    snippet = content[start : end + 1]
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[int, str] = {}
    for k, v in data.items():
        try:
            cid = int(k)
        except (ValueError, TypeError):
            continue
        if v in ("address", "reply", "ignore"):
            out[cid] = str(v)
    return out


def classify_comments(state: PRReviewState, config: RunnableConfig) -> dict:
    """C2 (ReAct, cheap tier): 各 comment を address / reply / ignore に分類。

    LLM 出力は {<id>: <class>} の object。指定されなかった id は ignore 扱い。
    """
    lcfg = _get_libmatic_config(config)
    if not state.comments:
        return {"classified": {}}

    agent = build_step_agent(
        step_name="pr_c2_classify_comments",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("pr_review/c2_classify_comments.md"),
    )

    payload = [c.model_dump() for c in state.comments]
    input_text = (
        f"## comments\n{json.dumps(payload, ensure_ascii=False)}\n"
    )
    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        classified = _parse_classification_object(_last_message_content(result))
    except Exception:
        classified = {}

    # 出力にない comment id は ignore に倒す
    for c in state.comments:
        classified.setdefault(c.id, "ignore")
    return {"classified": classified}


# --- C3: address_each (ReAct loop) ---


def address_each(state: PRReviewState, config: RunnableConfig) -> dict:
    """C3 (ReAct): address 対象 comment 毎に edit_file 等で対応。

    log は state.actions_log に積む。LLM が deferred 判定した comment は
    classified を ignore に降格 (reply 側に流れないように)。
    """
    lcfg = _get_libmatic_config(config)

    address_targets = [
        c for c in state.comments if state.classified.get(c.id) == "address"
    ]
    if not address_targets:
        return {"actions_log": list(state.actions_log)}

    agent = build_step_agent(
        step_name="pr_c3_address_each",
        config=lcfg,
        tools=[read_file, edit_file, write_file, bash],
        system_prompt=load_prompt("pr_review/c3_address_each.md"),
    )

    targets_payload = [c.model_dump() for c in address_targets]
    input_text = (
        f"## pr_number\n{state.pr_number}\n\n"
        f"## address_targets\n{json.dumps(targets_payload, ensure_ascii=False)}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        raw_log = _parse_json_array(_last_message_content(result))
    except Exception:
        raw_log = []

    new_classified = dict(state.classified)
    actions_log: list[dict] = list(state.actions_log)
    for entry in raw_log:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("comment_id")
        try:
            cid_int = int(cid) if cid is not None else None
        except (ValueError, TypeError):
            cid_int = None
        actions_log.append(
            {
                "comment_id": cid_int,
                "status": entry.get("status") or "deferred",
                "action_summary": entry.get("action_summary") or "",
                "files_touched": list(entry.get("files_touched") or []),
            }
        )
        # deferred は ignore に降格 (reply にも回さない、後で人間が判断)
        if cid_int is not None and entry.get("status") == "deferred":
            new_classified[cid_int] = "ignore"

    return {
        "actions_log": actions_log,
        "classified": new_classified,
    }


# --- C4: commit_push (deterministic) ---


def _has_staged_changes() -> bool:
    """git diff --cached --quiet で staged 差分の有無を判定 (差分あれば exit 1)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode != 0


def commit_push(state: PRReviewState, config: RunnableConfig) -> dict:
    """C4: 変更があれば git add -u → commit → push。何もなければ committed=False。"""
    _get_libmatic_config(config)

    if not state.actions_log:
        return {"committed": False}

    addressed = [a for a in state.actions_log if a.get("status") == "addressed"]
    if not addressed:
        return {"committed": False}

    files: list[str] = []
    for a in addressed:
        for f in a.get("files_touched") or []:
            if f and f not in files:
                files.append(f)

    try:
        if files:
            subprocess.run(["git", "add", *files], check=True)
        else:
            subprocess.run(["git", "add", "-u"], check=True)

        if not _has_staged_changes():
            return {"committed": False}

        commit_msg = f"fix: address PR #{state.pr_number} review comments"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"committed": False}

    return {"committed": True}


# --- C5: reply_comments (deterministic) ---


def _build_reply_body(comment_id: int, log_entry: dict | None, status: str) -> str:
    """対応内容に応じた reply 本文を組み立てる (deterministic、LLM 不要)。"""
    if status == "address" and log_entry and log_entry.get("status") == "addressed":
        summary = log_entry.get("action_summary") or "対応しました"
        files = log_entry.get("files_touched") or []
        body = f"対応しました: {summary}"
        if files:
            body += "\n\n変更ファイル: " + ", ".join(files)
        return body
    if status == "reply":
        return "ご指摘ありがとうございます。確認済みです。"
    # deferred / それ以外
    return "本指摘は本 PR では対応せず、追って別途対応します。"


def reply_comments(state: PRReviewState, config: RunnableConfig) -> dict:
    """C5: classified が address / reply のものに reply を投稿。

    address は actions_log の summary、reply は固定テンプレ、deferred は別途対応扱い。
    """
    _get_libmatic_config(config)

    log_by_id: dict[int, dict] = {}
    for a in state.actions_log:
        cid = a.get("comment_id")
        if isinstance(cid, int):
            log_by_id[cid] = a

    replied: list[int] = list(state.replied_comment_ids)
    for c in state.comments:
        if c.id in replied:
            continue
        cls = state.classified.get(c.id, "ignore")
        if cls == "ignore":
            continue
        body = _build_reply_body(c.id, log_by_id.get(c.id), cls)
        try:
            gh_pr_reply_core(state.pr_number, c.id, body)
            replied.append(c.id)
        except GhError:
            continue

    return {"replied_comment_ids": replied}
