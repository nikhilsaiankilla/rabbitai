"""
agent.py — LangGraph workflow entry point
Wires all 7 nodes into a directed graph and runs the full PR review pipeline.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, END

from nodes.fetcher import PRData, fetch_pr
from nodes.graph_builder import GraphInsight, build_dependency_graph
from nodes.classifier import ClassificationResult, classify_change
from nodes.embedder import EmbedResult, embed_and_store
from nodes.retriever import RetrievalResult, retrieve
from nodes.reviewer import ReviewResult, review
from nodes.poster import PostResult, post_comment
from utils.config import load_config


class ReviewState(TypedDict):
    config: dict
    repo_name: str
    pr_number: int
    pr: PRData | None
    graph_insight: GraphInsight | None
    classification: ClassificationResult | None
    embed_result: EmbedResult | None
    retrieval: RetrievalResult | None
    review_result: ReviewResult | None
    post_result: PostResult | None


def node_fetch(state: ReviewState) -> ReviewState:
    cfg = state["config"]
    pr = fetch_pr(cfg["github_token"], state["repo_name"], state["pr_number"])
    return {**state, "pr": pr}


def node_graph(state: ReviewState) -> ReviewState:
    pr = state["pr"]
    insight = build_dependency_graph(pr.files_changed, pr.diff)
    return {**state, "graph_insight": insight}


def node_classify(state: ReviewState) -> ReviewState:
    pr = state["pr"]
    result = classify_change(pr.title, pr.diff)
    return {**state, "classification": result}


def node_embed(state: ReviewState) -> ReviewState:
    pr = state["pr"]
    pr_id = f"{pr.repo_name}#{pr.pr_number}"
    result = embed_and_store(pr.diff, pr_id, state["config"])
    return {**state, "embed_result": result}


def node_retrieve(state: ReviewState) -> ReviewState:
    pr = state["pr"]
    classification = state["classification"]
    pr_id = f"{pr.repo_name}#{pr.pr_number}"

    # Build query from classification so retrieval is focused
    query = (
        f"{classification.change_type} review: "
        + ", ".join(classification.review_focus[:3])
    )

    result = retrieve(query, pr_id, state["config"])
    return {**state, "retrieval": result}


def node_review(state: ReviewState) -> ReviewState:
    result = review(
        pr=state["pr"],
        graph=state["graph_insight"],
        classification=state["classification"],
        retrieval=state["retrieval"],
        config=state["config"],
    )
    return {**state, "review_result": result}


def node_post(state: ReviewState) -> ReviewState:
    result = post_comment(
        review=state["review_result"],
        pr=state["pr"],
        config=state["config"],
    )
    return {**state, "post_result": result}


def build_graph() -> StateGraph:
    g = StateGraph(ReviewState)

    g.add_node("fetch", node_fetch)
    g.add_node("graph", node_graph)
    g.add_node("classify", node_classify)
    g.add_node("embed", node_embed)
    g.add_node("retrieve", node_retrieve)
    g.add_node("review", node_review)
    g.add_node("post", node_post)

    g.set_entry_point("fetch")

    # fetch → graph + classify + embed in sequence
    g.add_edge("fetch", "graph")
    g.add_edge("graph", "classify")
    g.add_edge("classify", "embed")
    g.add_edge("embed", "retrieve")
    g.add_edge("retrieve", "review")
    g.add_edge("review", "post")
    g.add_edge("post", END)

    return g.compile()


def run(repo_name: str, pr_number: int, config_path: str = "config.yaml") -> PostResult:
    """
    Main entry point — call this from GitHub Action, FastAPI, or CLI.

    Args:
        repo_name:   "owner/repo"
        pr_number:   PR number integer
        config_path: path to config.yaml

    Returns:
        PostResult with comment URL or skip reason
    """
    config = load_config(config_path)

    initial_state: ReviewState = {
        "config": config,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "pr": None,
        "graph_insight": None,
        "classification": None,
        "embed_result": None,
        "retrieval": None,
        "review_result": None,
        "post_result": None,
    }

    graph = build_graph()
    final_state = graph.invoke(initial_state)

    result = final_state["post_result"]
    print(f"[agent] {result.reason}")
    if result.comment_url:
        print(f"[agent] comment → {result.comment_url}")

    return result
