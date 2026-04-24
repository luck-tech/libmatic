"""LangChain tools for libmatic workflows.

実装状況 (Phase 1.4 完了時点):
- 完了: bash, fs (read/edit/write_file), search_sources, verify_coverage,
  fetch_source, fetch_x_thread, web_fetch, gh_* 全 6 関数
- Placeholder: web_search (NotImplementedError、v0.1 では LLM provider の
  built-in search を ReAct agent に bind する想定)

Phase 1.4 は完了。次は nodes/ 各 step の本実装 (Phase 1.3 の残り)。
extract_facts / fact_merger は prompt + ReAct agent 側で扱うため、
ここでは tool として export しない。
"""

from libmatic.tools.bash import bash
from libmatic.tools.coverage import (
    CoverageReport,
    CoverageStats,
    UncoveredClaim,
    verify_coverage,
)
from libmatic.tools.fs import edit_file, read_file, write_file
from libmatic.tools.github import (
    GhError,
    gh_issue_create,
    gh_issue_edit,
    gh_issue_list,
    gh_pr_comments,
    gh_pr_create,
    gh_pr_reply,
)
from libmatic.tools.search_sources import (
    Candidate,
    FeedEntry,
    search_sources,
)
from libmatic.tools.source import fetch_source, fetch_x_thread
from libmatic.tools.web import web_fetch, web_search

__all__ = [
    "Candidate",
    "CoverageReport",
    "CoverageStats",
    "FeedEntry",
    "GhError",
    "UncoveredClaim",
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
    "search_sources",
    "verify_coverage",
    "web_fetch",
    "web_search",
    "write_file",
]
