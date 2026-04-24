"""LangChain tools for libmatic workflows.

実装状況:
- 完了: bash, fs (read/edit/write_file), search_sources (PoC #1),
  verify_coverage (PoC #2)
- Stub (NotImplementedError): web, source, github

Phase 1.4 残り順序 (libmatic-oss-plan.md §3.3 d):
  3. fetch_source, fetch_x_thread (scripts/fetch_source.py, fetch_x.py 移植)
  4. extract_facts, web_fetch, web_search, github CLI wrapper
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
