"""
utils/config.py
Loads config.yaml and applies environment variable overrides.
Environment variables always take priority — this is how GitHub Actions injects secrets.

Priority (highest → lowest):
    1. Environment variables  ← GitHub Actions / CI
    2. config.yaml values     ← local dev
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

load_dotenv()


def load_config(path: str = "config.yaml") -> dict:
    """
    Load config from YAML file, then override with environment variables.

    Args:
        path: path to config file (default: config.yaml)

    Returns:
        Merged config dict ready for use across all nodes
    """
    config_path = Path(path)

    if config_path.exists():
        with open(config_path, "r") as f:
            config: dict = yaml.safe_load(f) or {}
    else:
        # In GitHub Actions there is no config.yaml — everything comes from env vars
        config = {}

    # Top level secrets
    if os.getenv("GEMINI_API_KEY"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY")

    if os.getenv("GITHUB_TOKEN"):
        config["github_token"] = os.getenv("GITHUB_TOKEN")

    if os.getenv("OPENAI_API_KEY"):
        config["openai_api_key"] = os.getenv("OPENAI_API_KEY")

    # Vector store
    vs = config.setdefault("vector_store", {})

    if os.getenv("VECTOR_STORE_PROVIDER"):
        vs["provider"] = os.getenv("VECTOR_STORE_PROVIDER")
    if os.getenv("PINECONE_API_KEY"):
        vs["api_key"] = os.getenv("PINECONE_API_KEY")
    if os.getenv("PINECONE_INDEX_NAME"):
        vs["index_name"] = os.getenv("PINECONE_INDEX_NAME")
    if os.getenv("QDRANT_HOST"):
        vs["host"] = os.getenv("QDRANT_HOST")
    if os.getenv("QDRANT_API_KEY"):
        vs["api_key"] = os.getenv("QDRANT_API_KEY")

    # Embedding provider
    emb = config.setdefault("embedding", {})

    if os.getenv("EMBEDDING_PROVIDER"):
        emb["provider"] = os.getenv("EMBEDDING_PROVIDER")
    if os.getenv("EMBEDDING_MODEL"):
        emb["model"] = os.getenv("EMBEDDING_MODEL")
    if os.getenv("OPENAI_API_KEY") and not emb.get("api_key"):
        emb["api_key"] = os.getenv("OPENAI_API_KEY")

    # LLM provider
    llm = config.setdefault("llm", {})

    if os.getenv("LLM_PROVIDER"):
        llm["provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_MODEL"):
        llm["model"] = os.getenv("LLM_MODEL")
    if os.getenv("OPENAI_API_KEY") and not llm.get("api_key"):
        llm["api_key"] = os.getenv("OPENAI_API_KEY")

    # Review behaviour
    review = config.setdefault("review", {})

    if os.getenv("REVIEW_LANGUAGE"):
        review["language"] = os.getenv("REVIEW_LANGUAGE")

    # Defaults
    review.setdefault("language", "typescript")
    review.setdefault("focus", ["bugs", "security", "performance"])
    review.setdefault("min_risk_score", 0)
    review.setdefault("post_score", True)

    config.setdefault("memory", {})
    config["memory"].setdefault("enabled", True)
    config["memory"].setdefault("repo_context", "")

    vs.setdefault("provider", "chromadb")
    vs.setdefault("path", "./chroma_db")
    vs.setdefault("collection", "pr-chunks")

    emb.setdefault("provider", "gemini")
    emb.setdefault("model", "")

    llm.setdefault("provider", "gemini")
    llm.setdefault("model", "")

    # Validation
    missing = []

    if not config.get("github_token"):
        missing.append("github_token (or GITHUB_TOKEN env var)")

    # At least one of Gemini or OpenAI must be configured
    has_gemini = bool(config.get("gemini_api_key"))
    has_openai = bool(config.get("openai_api_key"))
    if not has_gemini and not has_openai:
        missing.append(
            "gemini_api_key (or GEMINI_API_KEY) or openai_api_key (or OPENAI_API_KEY) — at least one required"
        )

    if missing:
        raise ValueError(
            "Missing required config values:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    return config
