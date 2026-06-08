"""
agent.py — LangGraph workflow entry point
Wires all 7 nodes + memory into a directed graph and runs the full PR review pipeline.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, END

from rabbitai.nodes.fetcher import PRData, fetch_pr
from rabbitai.nodes.graph_builder import GraphInsight, build_dependency_graph
from rabbitai.nodes.classifier import ClassificationResult, classify_change
from rabbitai.nodes.embedder import EmbedResult, embed_and_store
from rabbitai.nodes.retriever import RetrievalResult, retrieve
from rabbitai.nodes.reviewer import ReviewResult, review
from rabbitai.nodes.poster import PostResult, post_comment
from rabbitai.memory.repo_memory import MemoryResult, load_memory, save_memory
from rabbitai.utils.config import load_config


class ReviewState(TypedDict):
    config: dict
    repo_name: str
    pr_number: int
    pr: PRData | None
    graph_insight: GraphInsight | None
    classification: ClassificationResult | None
    embed_result: EmbedResult | None
    retrieval: RetrievalResult | None
    memory: MemoryResult | None
    review_result: ReviewResult | None
    post_result: PostResult | None


def node_fetch(state: ReviewState) -> ReviewState:
    print(
        f"\n [rabbitai] Fetching PR #{state['pr_number']} from {state['repo_name']}")
    cfg = state["config"]
    pr = fetch_pr(cfg["github_token"], state["repo_name"], state["pr_number"])
    print(
        f" [rabbitai] Fetched PR with {len(pr.files_changed)} changed files and {len(pr.diff)} lines of diff")
    return {**state, "pr": pr}


def node_graph(state: ReviewState) -> ReviewState:
    print(
        f"\n [rabbitai] Building dependency graph for PR #{state['pr_number']}...")
    pr = state["pr"]
    insight = build_dependency_graph(pr.files_changed, pr.diff)
    print(f" [rabbitai] Graph insight: {insight.summary}")
    return {**state, "graph_insight": insight}


def node_classify(state: ReviewState) -> ReviewState:
    print(f"\n [rabbitai] Classifying changes for PR #{state['pr_number']}...")
    pr = state["pr"]
    result = classify_change(pr.title, pr.diff)
    print(f" [rabbitai] Classification result: {result.change_type}")
    return {**state, "classification": result}


def node_embed(state: ReviewState) -> ReviewState:
    pr = state["pr"]
    pr_id = f"{pr.repo_name} #{pr.pr_number}"
    print(f" [rabbitai] Embedding PR {pr_id}...")
    result = embed_and_store(pr.diff, pr_id, state["config"])
    print(f" [rabbitai] Embed done — {result.chunks_stored} chunks stored")
    return {**state, "embed_result": result}


def node_retrieve(state: ReviewState) -> ReviewState:
    print(
        f"\n [rabbitai] Retrieving relevant past reviews for PR #{state['pr_number']}...")
    pr = state["pr"]
    classification = state["classification"]
    pr_id = f"{pr.repo_name}#{pr.pr_number}"

    query = (
        f"{classification.change_type} review: "
        + ", ".join(classification.review_focus[:3])
    )

    result = retrieve(query, pr_id, state["config"])
    print(f" [rabbitai] Retrieved {result.total_found} relevant chunks")
    return {**state, "retrieval": result}


def node_load_memory(state: ReviewState) -> ReviewState:
    print(f"\n [rabbitai] Loading past learnings for {state['repo_name']}...")
    mem = load_memory(state["repo_name"], state["config"])
    print(f" [rabbitai] Loaded memory with {len(mem.entries)} entries")
    return {**state, "memory": mem}


def node_review(state: ReviewState) -> ReviewState:
    print(f"\n [rabbitai] Reviewing PR #{state['pr_number']}...")
    result = review(
        pr=state["pr"],
        graph=state["graph_insight"],
        classification=state["classification"],
        retrieval=state["retrieval"],
        memory=state["memory"],
        config=state["config"],
    )
    print(f" [rabbitai] Review completed for PR #{state['pr_number']}")
    return {**state, "review_result": result}


def node_post(state: ReviewState) -> ReviewState:
    print(
        f"\n [rabbitai] Posting review comment for PR #{state['pr_number']}...")
    result = post_comment(
        review=state["review_result"],
        pr=state["pr"],
        config=state["config"],
    )
    print(f" [rabbitai] Posted review comment for PR #{state['pr_number']}")
    return {**state, "post_result": result}


def node_save_memory(state: ReviewState) -> ReviewState:
    print(
        f"\n [rabbitai] Saving learnings for {state['repo_name']}...")
    review_result = state["review_result"]
    if review_result:
        save_memory(state["repo_name"], review_result.raw, state["config"])
    print(f" [rabbitai] Saved learnings for {state['repo_name']}")
    return state


def build_graph() -> StateGraph:
    g = StateGraph(ReviewState)

    g.add_node("fetch", node_fetch)
    g.add_node("graph", node_graph)
    g.add_node("classify", node_classify)
    g.add_node("embed", node_embed)
    g.add_node("retrieve", node_retrieve)
    g.add_node("load_memory", node_load_memory)
    g.add_node("review", node_review)
    g.add_node("post", node_post)
    g.add_node("save_memory", node_save_memory)

    g.set_entry_point("fetch")

    g.add_edge("fetch", "graph")
    g.add_edge("graph", "classify")
    g.add_edge("classify", "embed")
    g.add_edge("embed", "retrieve")
    g.add_edge("retrieve", "load_memory")   # load past learnings before review
    g.add_edge("load_memory", "review")
    g.add_edge("review", "post")
    g.add_edge("post", "save_memory")       # save new learnings after posting
    g.add_edge("save_memory", END)

    return g.compile()


def run(repo_name: str, pr_number: int, config_path: str = "config.yaml") -> PostResult:
    print(f"[rabbitai] Starting review for {repo_name} PR #{pr_number}...")
    """
    Main entry point — called from GitHub Action, MCP server, or CLI.

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
        "memory": None,
        "review_result": None,
        "post_result": None,
    }

    graph = build_graph()
    final_state = graph.invoke(initial_state)

    result = final_state["post_result"]
    print(f"[rabbitai] {result.reason}")
    if result.comment_url:
        print(f"[rabbitai] comment → {result.comment_url}")

    print(f"[rabbitai] Finished review for {repo_name} PR #{pr_number}")
    return result
