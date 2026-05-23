"""
Node 6 — Reviewer
Builds the review prompt from all upstream node outputs and
streams a structured review from Gemini.
"""

from __future__ import annotations

from dataclasses import dataclass

from google import genai

from memory.repo_memory import MemoryResult
from nodes.fetcher import PRData, diff_summary
from nodes.graph_builder import GraphInsight, format_for_prompt as graph_prompt
from nodes.classifier import ClassificationResult, format_for_prompt as classify_prompt
from nodes.retriever import RetrievalResult, format_for_prompt as retrieval_prompt


@dataclass
class ReviewResult:
    raw: str                  # full Gemini response
    score: int | None         # 1-10 if post_score enabled
    pr_id: str


def _build_prompt(
    pr: PRData,
    graph: GraphInsight,
    classification: ClassificationResult,
    retrieval: RetrievalResult,
    repo_context: str,
    config: dict,
) -> str:
    review_cfg = config.get("review", {})
    language = review_cfg.get("language", "unknown")
    focus = review_cfg.get("focus", ["bugs", "security", "performance"])
    post_score = review_cfg.get("post_score", True)

    focus_str = ", ".join(focus)

    score_instruction = (
        "End your response with a line: SCORE: <number>/10\n" if post_score else ""
    )

    return f"""You are an expert code reviewer. Review this pull request and post structured, actionable feedback.

PR SUMMARY
{diff_summary(pr)}

REPO CONTEXT
{repo_context or "No repo context provided."}

CHANGE CLASSIFICATION
{classify_prompt(classification)}

BLAST RADIUS (dependency graph)
{graph_prompt(graph)}

RELEVANT DIFF CHUNKS
{retrieval_prompt(retrieval)}

FULL DIFF
{pr.diff}

INSTRUCTIONS
- Language: {language}
- Focus on: {focus_str}
- Be specific — include filename and line number for every issue
- Group findings by severity using these exact headers:
  [BUG] for bugs and logic errors
  [SECURITY] for security vulnerabilities
  [PERFORMANCE] for performance issues
  [GOOD] for positive notes worth calling out
- Keep suggestions concise and actionable
- If no issues found in a category, skip that category
{score_instruction}
Output only the review. No preamble.
"""


def _parse_score(text: str) -> int | None:
    import re
    match = re.search(r"SCORE:\s*(\d+)\s*/\s*10", text, re.IGNORECASE)
    if match:
        return max(1, min(10, int(match.group(1))))
    return None


def review(
    pr: PRData,
    graph: GraphInsight,
    classification: ClassificationResult,
    retrieval: RetrievalResult,
    memory: "MemoryResult | None",
    config: dict,
) -> ReviewResult:
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "gemini").lower()

    if provider == "gemini":
        from google import genai
        client = genai.Client(api_key=config["gemini_api_key"])
        model = llm_cfg.get("model") or "gemini-2.0-flash"

        repo_context = memory.context if (memory and memory.context) else config.get(
            "memory", {}).get("repo_context", "")
        prompt = _build_prompt(pr, graph, classification,
                               retrieval, repo_context, config)

        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.strip()

    elif provider == "openai":
        from openai import OpenAI
        api_key = llm_cfg.get("api_key") or config.get("openai_api_key")
        client = OpenAI(api_key=api_key)
        model = llm_cfg.get("model") or "gpt-4o-mini"

        repo_context = memory.context if (memory and memory.context) else config.get(
            "memory", {}).get("repo_context", "")
        prompt = _build_prompt(pr, graph, classification,
                               retrieval, repo_context, config)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. Supported: gemini, openai")

    pr_id = f"{pr.repo_name}#{pr.pr_number}"

    return ReviewResult(
        raw=raw,
        score=_parse_score(raw),
        pr_id=pr_id,
    )
