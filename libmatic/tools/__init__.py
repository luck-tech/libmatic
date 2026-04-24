"""LangChain tools for libmatic workflows.

Phase 1.3: signature 定義のみ (fs / bash は実装済み、他は NotImplementedError)。
Phase 1.4 で順次実装:
  1. search_sources (scripts/search_sources.py 移植) — 最初の PoC
  2. verify_coverage (scripts/verify_coverage.py 移植) — hybrid node の練習
  3. fetch_source, fetch_x_thread (scripts/fetch_source.py, fetch_x.py 移植)
  4. extract_facts, web_fetch, web_search は ReAct agent 側で使用
"""

from libmatic.tools.bash import bash
from libmatic.tools.coverage import verify_coverage
from libmatic.tools.fs import edit_file, read_file, write_file
from libmatic.tools.github import (
    gh_issue_create,
    gh_issue_edit,
    gh_issue_list,
    gh_pr_comments,
    gh_pr_create,
    gh_pr_reply,
)
from libmatic.tools.source import fetch_source, fetch_x_thread
from libmatic.tools.web import web_fetch, web_search

__all__ = [
    "bash",
    "edit_file",
    "fetch_source",
    "fetch_x_thread",
    "gh_issue_create",
    "gh_issue_edit",
    "gh_issue_list",
    "gh_pr_comments",
    "gh_pr_create",
    "gh_pr_reply",
    "read_file",
    "verify_coverage",
    "web_fetch",
    "web_search",
    "write_file",
]
