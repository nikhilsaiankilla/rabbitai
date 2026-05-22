"""
memory/repo_memory.py
Persistent memory across PR reviews using mem0.
Remembers repo conventions, recurring issues, and codebase patterns.

Flow in agent.py:
    fetch → graph → classify → embed → retrieve → load_memory → review → post → save_memory
"""

from __future__ import annotations

from dataclasses import dataclass

from mem0 import Memory


@dataclass
class MemoryResult:
    context: str        # formatted string injected into review prompt
    entries: list[str]  # raw memory entries retrieved
    repo_id: str        # user_id used in mem0 — derived from repo name


def _get_client() -> Memory:
    return Memory()


def _repo_id(repo_name: str) -> str:
    # mem0 uses user_id as the memory namespace
    # "nikhilsaiankilla/rabbitai" → "nikhilsaiankilla_rabbitai"
    return repo_name.replace("/", "_").replace("-", "_").lower()


def load_memory(repo_name: str, config: dict) -> MemoryResult:
    """
    Load past learnings for this repo from mem0.
    Called BEFORE the review node so context is injected into the prompt.

    Args:
        repo_name: "owner/repo"
        config:    parsed config.yaml dict

    Returns:
        MemoryResult with formatted context string
    """
    if not config.get("memory", {}).get("enabled", True):
        return MemoryResult(context="", entries=[], repo_id="")

    repo_id = _repo_id(repo_name)
    m = _get_client()

    # Search for anything relevant to code review patterns in this repo
    results = m.search(
        query="repo conventions patterns recurring issues code style",
        user_id=repo_id,
        limit=10,
    )

    if not results:
        return MemoryResult(context="", entries=[], repo_id=repo_id)

    entries = [r.get("memory", "") for r in results if r.get("memory")]

    if not entries:
        return MemoryResult(context="", entries=[], repo_id=repo_id)

    context = "Past learnings from previous PR reviews on this repo:\n" + "\n".join(
        f"- {e}" for e in entries
    )

    return MemoryResult(context=context, entries=entries, repo_id=repo_id)


def save_memory(repo_name: str, review_text: str, config: dict) -> None:
    """
    Save learnings from this review to mem0 for future PRs.
    Called AFTER the review node.

    Args:
        repo_name:   "owner/repo"
        review_text: raw Gemini review output
        config:      parsed config.yaml dict
    """
    if not config.get("memory", {}).get("enabled", True):
        return

    repo_id = _repo_id(repo_name)
    m = _get_client()

    # mem0 automatically extracts and deduplicates facts from the text
    m.add(review_text, user_id=repo_id)
