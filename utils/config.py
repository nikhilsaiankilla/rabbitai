"""
utils/config.py
Loads config.yaml and applies environment variable overrides.
Environment variables take priority — this is how GitHub Actions injects secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_config(path: str = "config.yaml") -> dict:
    """
    Load config from YAML file, then override with environment variables.

    Priority (highest → lowest):
        1. Environment variables  ← GitHub Actions / CI injects these
        2. config.yaml values     ← local dev

    Args:
        path: path to config file (default: config.yaml)

    Returns:
        Merged config dict
    """
    config_path = Path(path)

    if config_path.exists():
        with open(config_path, "r") as f:
            config: dict = yaml.safe_load(f) or {}
    else:
        # In GitHub Actions we won't have a config.yaml —
        # everything comes from env vars. That's fine.
        config = {}

    # Top-level secrets (env vars always win)
    if os.getenv("GEMINI_API_KEY"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY")

    if os.getenv("GITHUB_TOKEN"):
        config["github_token"] = os.getenv("GITHUB_TOKEN")

    # Vector store env overrides
    vs = config.setdefault("vector_store", {})

    if os.getenv("VECTOR_STORE_PROVIDER"):
        vs["provider"] = os.getenv("VECTOR_STORE_PROVIDER")
    if os.getenv("PINECONE_API_KEY"):
        vs["api_key"] = os.getenv("PINECONE_API_KEY")
    if os.getenv("QDRANT_HOST"):
        vs["host"] = os.getenv("QDRANT_HOST")
    if os.getenv("QDRANT_API_KEY"):
        vs["api_key"] = os.getenv("QDRANT_API_KEY")

    # Defaults (so nodes never get KeyError)
    config.setdefault("review", {})
    config["review"].setdefault("language", "typescript")
    config["review"].setdefault("focus", ["bugs", "security", "performance"])
    config["review"].setdefault("min_risk_score", 0)
    config["review"].setdefault("post_score", True)

    config.setdefault("memory", {})
    config["memory"].setdefault("repo_context", "")

    vs.setdefault("provider", "chromadb")
    vs.setdefault("path", "./chroma_db")
    vs.setdefault("collection", "pr-chunks")

    # Validation
    missing = []
    if not config.get("gemini_api_key"):
        missing.append("gemini_api_key (or GEMINI_API_KEY env var)")
    if not config.get("github_token"):
        missing.append("github_token (or GITHUB_TOKEN env var)")

    if missing:
        raise ValueError(
            f"Missing required config values:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    return config