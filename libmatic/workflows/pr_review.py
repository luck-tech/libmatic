"""Workflow C: address-pr-comments graph definition."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from libmatic.nodes import pr_review as nodes
from libmatic.state.pr_review import PRReviewState


def build_pr_review_graph() -> StateGraph:
    g: StateGraph = StateGraph(PRReviewState)

    g.add_node("c1_collect_comments", nodes.collect_comments)
    g.add_node("c2_classify_comments", nodes.classify_comments)
    g.add_node("c3_address_each", nodes.address_each)
    g.add_node("c4_commit_push", nodes.commit_push)
    g.add_node("c5_reply_comments", nodes.reply_comments)

    g.add_edge(START, "c1_collect_comments")
    g.add_edge("c1_collect_comments", "c2_classify_comments")
    g.add_edge("c2_classify_comments", "c3_address_each")
    g.add_edge("c3_address_each", "c4_commit_push")
    g.add_edge("c4_commit_push", "c5_reply_comments")
    g.add_edge("c5_reply_comments", END)

    return g
