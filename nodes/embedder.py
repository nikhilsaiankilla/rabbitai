"""
Node 3 — Embedder
Chunks the PR diff by file, embeds each chunk via Gemini,
and stores in ChromaDB (or any vector store the user configures).

Config-driven: user provides vector store details in config.yaml.
Supports: chromadb (local), pinecone, qdrant — add more via PROVIDERS map.

config.yaml shape expected:
    gemini_api_key: "xxx"

    vector_store:
      provider: "chromadb"        # chromadb | pinecone | qdrant
      path: "./chroma_db"         # chromadb only — local folder
      api_key: "xxx"              # pinecone / qdrant cloud
      host: "localhost"           # qdrant self-host
      port: 6333                  # qdrant self-host
      index_name: "code-review"   # pinecone index name
      collection: "pr-chunks"     # collection / namespace name
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import google.generativeai as genai


# Data types
@dataclass
class DiffChunk:
    chunk_id: str           # sha256 of (pr_id + filename + content)
    pr_id: str              # "{owner}/{repo}#{pr_number}"
    filename: str
    content: str            # the actual diff text for this file
    added_lines: int
    removed_lines: int
    metadata: dict = field(default_factory=dict)


@dataclass
class EmbedResult:
    chunks_stored: int
    collection: str
    pr_id: str
    skipped: int            # chunks already in store (idempotent re-runs)
    chunk_ids: list[str]


# Chunking
def _chunk_diff_by_file(diff: str, pr_id: str) -> list[DiffChunk]:
    """
    Split full diff into one chunk per file.
    Expects the header format from fetcher.py:
        ### FILE: src/auth.ts  [modified]  +12 -3
    Falls back to standard unified diff headers (--- a/file) if needed.
    """
    chunks: list[DiffChunk] = []
    current_file: str | None = None
    current_lines: list[str] = []

    def _flush(filename: str, lines: list[str]) -> None:
        content = "\n".join(lines).strip()
        if not content:
            return
        added = sum(1 for l in lines if l.startswith(
            "+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-")
                      and not l.startswith("---"))
        chunk_id = hashlib.sha256(
            f"{pr_id}::{filename}::{content}".encode()
        ).hexdigest()[:16]
        chunks.append(DiffChunk(
            chunk_id=chunk_id,
            pr_id=pr_id,
            filename=filename,
            content=content,
            added_lines=added,
            removed_lines=removed,
            metadata={"pr_id": pr_id, "filename": filename},
        ))

    for line in diff.splitlines():
        # fetcher.py style header
        if line.startswith("### FILE:"):
            if current_file and current_lines:
                _flush(current_file, current_lines)
            current_file = line.split("  ")[0].replace("### FILE:", "").strip()
            current_lines = []
            continue

        # Standard unified diff fallback
        if line.startswith("diff --git"):
            if current_file and current_lines:
                _flush(current_file, current_lines)
            current_file = line.split(
                " b/")[-1].strip() if " b/" in line else line
            current_lines = []
            continue

        if current_file is not None:
            current_lines.append(line)

    if current_file and current_lines:
        _flush(current_file, current_lines)

    return chunks


# Embedding via Gemini
def _embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """
    Embed a list of texts using Gemini text-embedding-004.
    Returns list of float vectors.
    """
    genai.configure(api_key=api_key)
    vectors = []
    for text in texts:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        vectors.append(result["embedding"])
        time.sleep(0.1)   # stay within free-tier rate limits
    return vectors


# ── Vector store backends 
def _get_chromadb_collection(cfg: dict):
    import chromadb
    path = cfg.get("path", "./chroma_db")
    client = chromadb.PersistentClient(path=path)
    collection_name = cfg.get("collection", "pr-chunks")
    return client.get_or_create_collection(collection_name)


def _get_pinecone_index(cfg: dict):
    from pinecone import Pinecone
    pc = Pinecone(api_key=cfg["api_key"])
    index_name = cfg.get("index_name", "code-review")
    return pc.Index(index_name)


def _get_qdrant_client(cfg: dict):
    from qdrant_client import QdrantClient
    if cfg.get("api_key"):
        # Qdrant cloud
        return QdrantClient(url=cfg["host"], api_key=cfg["api_key"])
    return QdrantClient(host=cfg.get("host", "localhost"), port=cfg.get("port", 6333))


def _store_chromadb(collection, chunks: list[DiffChunk], vectors: list[list[float]]) -> int:
    existing = set(collection.get(ids=[c.chunk_id for c in chunks])["ids"])
    new_chunks = [(c, v) for c, v in zip(chunks, vectors)
                  if c.chunk_id not in existing]
    if not new_chunks:
        return 0
    collection.add(
        ids=[c.chunk_id for c, _ in new_chunks],
        embeddings=[v for _, v in new_chunks],
        documents=[c.content for c, _ in new_chunks],
        metadatas=[c.metadata for c, _ in new_chunks],
    )
    return len(new_chunks)


def _store_pinecone(index, chunks: list[DiffChunk], vectors: list[list[float]], namespace: str) -> int:
    upserts = [
        {
            "id": c.chunk_id,
            "values": v,
            "metadata": {**c.metadata, "content": c.content[:1000]},
        }
        for c, v in zip(chunks, vectors)
    ]
    index.upsert(vectors=upserts, namespace=namespace)
    return len(upserts)


def _store_qdrant(client, chunks: list[DiffChunk], vectors: list[list[float]], cfg: dict) -> int:
    from qdrant_client.models import PointStruct, VectorParams, Distance
    collection_name = cfg.get("collection", "pr-chunks")
    existing_collections = [
        c.name for c in client.get_collections().collections]
    if collection_name not in existing_collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=len(vectors[0]), distance=Distance.COSINE),
        )
    points = [
        PointStruct(
            id=abs(hash(c.chunk_id)) % (2**63),
            vector=v,
            payload={**c.metadata, "chunk_id": c.chunk_id,
                     "content": c.content[:1000]},
        )
        for c, v in zip(chunks, vectors)
    ]
    client.upsert(collection_name=collection_name, points=points)
    return len(points)


# ── Public entry point
def embed_and_store(
    diff: str,
    pr_id: str,
    config: dict,
) -> EmbedResult:
    """
    Main function called by agent.py (Node 3).

    Args:
        diff:    full diff string from fetcher.py Node 1
        pr_id:   "{owner}/{repo}#{pr_number}"
        config:  parsed config.yaml dict

    Returns:
        EmbedResult with storage stats
    """
    gemini_api_key: str = config["gemini_api_key"]
    vs_cfg: dict = config.get("vector_store", {})
    provider: str = vs_cfg.get("provider", "chromadb").lower()
    collection_name: str = vs_cfg.get("collection", "pr-chunks")

    # 1. Chunk
    chunks = _chunk_diff_by_file(diff, pr_id)
    if not chunks:
        return EmbedResult(
            chunks_stored=0, collection=collection_name,
            pr_id=pr_id, skipped=0, chunk_ids=[],
        )

    # 2. Embed
    texts = [c.content for c in chunks]
    vectors = _embed_texts(texts, gemini_api_key)

    # 3. Store
    stored = 0
    skipped = len(chunks)

    if provider == "chromadb":
        collection = _get_chromadb_collection(vs_cfg)
        stored = _store_chromadb(collection, chunks, vectors)

    elif provider == "pinecone":
        index = _get_pinecone_index(vs_cfg)
        stored = _store_pinecone(
            index, chunks, vectors, namespace=collection_name)

    elif provider == "qdrant":
        client = _get_qdrant_client(vs_cfg)
        stored = _store_qdrant(client, chunks, vectors, vs_cfg)

    else:
        raise ValueError(
            f"Unknown vector_store provider: '{provider}'. "
            "Supported: chromadb, pinecone, qdrant"
        )

    skipped = len(chunks) - stored

    return EmbedResult(
        chunks_stored=stored,
        collection=collection_name,
        pr_id=pr_id,
        skipped=skipped,
        chunk_ids=[c.chunk_id for c in chunks],
    )


def format_for_prompt(result: EmbedResult) -> str:
    """Inject embed stats into the review prompt."""
    return (
        f"Embedded {result.chunks_stored} diff chunk(s) into '{result.collection}' "
        f"({result.skipped} already cached). PR: {result.pr_id}"
    )
