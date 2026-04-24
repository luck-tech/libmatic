"""Workflow B: topic-debate (9 step) graph definition.

See docs/ARCHITECTURE.md §3 for the graph diagram.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from libmatic.nodes import topic_debate as nodes
from libmatic.state.topic_debate import TopicDebateState


def build_topic_debate_graph() -> StateGraph:
    """Build StateGraph for topic-debate workflow.

    Phase 1.3 時点では node 実体は NotImplementedError を投げる stub なので、
    `.compile()` まではできるが実行はできない。
    """
    g: StateGraph = StateGraph(TopicDebateState)

    g.add_node("step1_source_collector", nodes.source_collector)
    g.add_node("step2_source_scorer", nodes.source_scorer)
    g.add_node("step3_source_fetcher", nodes.source_fetcher)
    g.add_node("step4_fact_extractor", nodes.fact_extractor)
    g.add_node("step5_fact_merger", nodes.fact_merger)
    g.add_node("step6_coverage_verifier", nodes.coverage_verifier)
    g.add_node("step7_article_writer", nodes.article_writer)
    g.add_node("step8_expanded_writer", nodes.expanded_writer)
    g.add_node("step9_pr_opener", nodes.pr_opener)

    g.add_edge(START, "step1_source_collector")
    g.add_edge("step1_source_collector", "step2_source_scorer")
    g.add_edge("step2_source_scorer", "step3_source_fetcher")
    g.add_edge("step3_source_fetcher", "step4_fact_extractor")
    g.add_edge("step4_fact_extractor", "step5_fact_merger")
    g.add_edge("step5_fact_merger", "step6_coverage_verifier")

    # step 6 で coverage 未達なら step 3 にループ (最大 2 回)
    g.add_conditional_edges(
        "step6_coverage_verifier",
        nodes.coverage_gate,
        {
            "step7_article_writer": "step7_article_writer",
            "step3_source_fetcher": "step3_source_fetcher",
        },
    )
    g.add_edge("step7_article_writer", "step8_expanded_writer")
    g.add_edge("step8_expanded_writer", "step9_pr_opener")
    g.add_edge("step9_pr_opener", END)

    return g
