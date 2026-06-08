"""
Node 5 — Retriever
Semantic search over stored diff chunks using the user's configured vector store.
Returns the most relevant chunks to feed into the Gemini review prompt.

Mirrors the provider pattern from embedder.py — fully config-driven.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from dataclasses_json import config
import google.generativeai as genai


@dataclass
class RetrievedChunk:
    chunk_id: str
    filename: str
    content: str
    score: float            # similarity score 0-1
    pr_id: str


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    query: str
    total_found: int


def _embed_query(query: str, config: dict) -> list[float]:
    embed_cfg = config.get("embedding", {})
    provider = embed_cfg.get("provider", "gemini").lower()

    if provider == "gemini":
        import google.generativeai as genai
        api_key = config["gemini_api_key"]
        model = embed_cfg.get("model", "models/gemini-embedding-001")
        client = genai.Client(api_key=api_key, http_options={
                              "api_version": "v1"})
        result = client.models.embed_content(model=model, contents=query)
        return list(result.embeddings[0].values)

    elif provider == "openai":
        from openai import OpenAI
        api_key = embed_cfg.get("api_key") or config.get("openai_api_key")
        model = embed_cfg.get("model", "text-embedding-3-small")
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model=model, input=query)
        return response.data[0].embedding

    else:
        raise ValueError(f"Unknown embedding provider: '{provider}'")


def _query_chromadb(cfg: dict, vector: list[float], pr_id: str, top_k: int) -> list[RetrievedChunk]:
    import chromadb
    client = chromadb.PersistentClient(path=cfg.get("path", "./chroma_db"))
    collection = client.get_or_create_collection(
        cfg.get("collection", "pr-chunks"))
    results = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
        where={"pr_id": pr_id},
    )
    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i]
        chunks.append(RetrievedChunk(
            chunk_id=results["ids"][0][i],
            filename=meta.get("filename", ""),
            content=doc,
            score=round(1 - dist, 4),
            pr_id=meta.get("pr_id", pr_id),
        ))
    return chunks


def _query_pinecone(cfg: dict, vector: list[float], pr_id: str, top_k: int) -> list[RetrievedChunk]:
    from pinecone import Pinecone
    pc = Pinecone(api_key=cfg["api_key"])
    index = pc.Index(cfg.get("index_name", "code-review"))
    results = index.query(
        vector=vector,
        top_k=top_k,
        namespace=cfg.get("collection", "pr-chunks"),
        filter={"pr_id": pr_id},
        include_metadata=True,
    )
    chunks = []
    for match in results["matches"]:
        meta = match["metadata"]
        chunks.append(RetrievedChunk(
            chunk_id=match["id"],
            filename=meta.get("filename", ""),
            content=meta.get("content", ""),
            score=round(match["score"], 4),
            pr_id=meta.get("pr_id", pr_id),
        ))
    return chunks


def _query_qdrant(cfg: dict, vector: list[float], pr_id: str, top_k: int) -> list[RetrievedChunk]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    if cfg.get("api_key"):
        client = QdrantClient(url=cfg["host"], api_key=cfg["api_key"])
    else:
        client = QdrantClient(host=cfg.get(
            "host", "localhost"), port=cfg.get("port", 6333))

    results = client.search(
        collection_name=cfg.get("collection", "pr-chunks"),
        query_vector=vector,
        limit=top_k,
        query_filter=Filter(
            must=[FieldCondition(key="pr_id", match=MatchValue(value=pr_id))]
        ),
    )
    chunks = []
    for hit in results:
        payload = hit.payload or {}
        chunks.append(RetrievedChunk(
            chunk_id=payload.get("chunk_id", str(hit.id)),
            filename=payload.get("filename", ""),
            content=payload.get("content", ""),
            score=round(hit.score, 4),
            pr_id=payload.get("pr_id", pr_id),
        ))
    return chunks


def retrieve(
    query: str,
    pr_id: str,
    config: dict,
    top_k: int = 5,
) -> RetrievalResult:
    """
    Main function called by agent.py (Node 5).

    Args:
        query:   natural language query built from classification result
        pr_id:   "{owner}/{repo}#{pr_number}"
        config:  parsed config.yaml dict
        top_k:   number of chunks to retrieve

    Returns:
        RetrievalResult with ranked chunks
    """
    vs_cfg: dict = config.get("vector_store", {})
    provider: str = vs_cfg.get("provider", "chromadb").lower()

    vector = _embed_query(query, config)

    if provider == "chromadb":
        chunks = _query_chromadb(vs_cfg, vector, pr_id, top_k)
    elif provider == "pinecone":
        chunks = _query_pinecone(vs_cfg, vector, pr_id, top_k)
    elif provider == "qdrant":
        chunks = _query_qdrant(vs_cfg, vector, pr_id, top_k)
    else:
        raise ValueError(
            f"Unknown vector_store provider: '{provider}'. "
            "Supported: chromadb, pinecone, qdrant"
        )

    chunks.sort(key=lambda c: c.score, reverse=True)

    return RetrievalResult(chunks=chunks, query=query, total_found=len(chunks))


def format_for_prompt(result: RetrievalResult) -> str:
    """Format retrieved chunks to inject into the Gemini review prompt."""
    if not result.chunks:
        return "No relevant chunks retrieved."

    parts = [
        f"Top {len(result.chunks)} relevant diff chunks (query: \"{result.query}\"):\n"]
    for i, chunk in enumerate(result.chunks, 1):
        parts.append(
            f"[{i}] {chunk.filename} (score: {chunk.score})\n"
            f"{chunk.content[:800]}\n"
        )
    return "\n".join(parts)
