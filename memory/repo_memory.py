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


def _get_client(config: dict) -> Memory:
    """
    Build mem0 Memory client using the embedding provider from config.yaml.
    Mirrors the same provider the user chose for embedder.py and retriever.py.
    """
    embed_cfg = config.get("embedding", {})
    provider = embed_cfg.get("provider", "gemini").lower()

    if provider == "gemini":
        mem_config = {
            "embedder": {
                "provider": "gemini",
                "config": {
                    "model": embed_cfg.get("model") or "models/gemini-embedding-001",
                    "api_key": config.get("gemini_api_key"),
                },
            },
            "llm": {
                "provider": "gemini",
                "config": {
                    "model": "gemini-2.0-flash",
                    "api_key": config.get("gemini_api_key"),
                },
            },
        }

    elif provider == "openai":
        api_key = embed_cfg.get("api_key") or config.get("openai_api_key")
        mem_config = {
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": embed_cfg.get("model") or "text-embedding-3-small",
                    "api_key": api_key,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4.1-mini",
                    "api_key": api_key,
                },
            },
        }

    else:
        raise ValueError(
            f"Unsupported embedding provider for mem0: '{provider}'. "
            "Supported: gemini, openai"
        )

    return Memory.from_config(mem_config)


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

    try:
        m = _get_client(config)
        results = m.search(
            query="repo conventions patterns recurring issues code style",
            user_id=repo_id,
            limit=10,
        )
    except Exception as e:
        # Memory failure should never block a review
        print(f" [memory] Warning: failed to load memory — {e}")
        return MemoryResult(context="", entries=[], repo_id=repo_id)

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

    try:
        m = _get_client(config)
        # mem0 automatically extracts and deduplicates facts from the text
        m.add(review_text, user_id=repo_id)
    except Exception as e:
        # Memory failure should never block a review
        print(f" [memory] Warning: failed to save memory — {e}")
