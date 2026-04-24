"""Workflow graph が build/compile できるかのスモーク test。

node 実体は Phase 1.3 では NotImplementedError の stub なので、
`.compile()` まで通ることだけを確認する（実行はしない）。
"""

from __future__ import annotations

from libmatic.workflows.pr_review import build_pr_review_graph
from libmatic.workflows.suggest_topics import build_suggest_topics_graph
from libmatic.workflows.topic_debate import build_topic_debate_graph


def test_topic_debate_graph_builds_and_compiles() -> None:
    g = build_topic_debate_graph()
    compiled = g.compile()
    assert compiled is not None
    # 9 step + START/END が登録されている
    assert "step1_source_collector" in g.nodes
    assert "step9_pr_opener" in g.nodes


def test_suggest_topics_graph_builds_and_compiles() -> None:
    g = build_suggest_topics_graph()
    compiled = g.compile()
    assert compiled is not None
    assert "a1_load_priorities" in g.nodes
    assert "a6_propose_new_sources" in g.nodes


def test_pr_review_graph_builds_and_compiles() -> None:
    g = build_pr_review_graph()
    compiled = g.compile()
    assert compiled is not None
    assert "c1_collect_comments" in g.nodes
    assert "c5_reply_comments" in g.nodes
