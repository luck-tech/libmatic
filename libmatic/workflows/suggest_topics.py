"""Workflow A: suggest-topics graph definition."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from libmatic.nodes import suggest_topics as nodes
from libmatic.state.suggest_topics import SuggestTopicsState


def build_suggest_topics_graph() -> StateGraph:
    g: StateGraph = StateGraph(SuggestTopicsState)

    g.add_node("a1_load_priorities", nodes.load_priorities)
    g.add_node("a2_fetch_candidates", nodes.fetch_candidates)
    g.add_node("a3_relevance_filter", nodes.relevance_filter)
    g.add_node("a4_dedup_against_issues", nodes.dedup_against_issues)
    g.add_node("a5_create_issues", nodes.create_issues)
    g.add_node("a6_propose_new_sources", nodes.propose_new_sources)

    g.add_edge(START, "a1_load_priorities")
    g.add_edge("a1_load_priorities", "a2_fetch_candidates")
    g.add_edge("a2_fetch_candidates", "a3_relevance_filter")
    g.add_edge("a3_relevance_filter", "a4_dedup_against_issues")
    g.add_edge("a4_dedup_against_issues", "a5_create_issues")
    g.add_edge("a5_create_issues", "a6_propose_new_sources")
    g.add_edge("a6_propose_new_sources", END)

    return g
