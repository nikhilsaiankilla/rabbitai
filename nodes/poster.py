"""
Node 7 — Poster
Formats the review result and posts it as a GitHub PR comment.
Cleans up the SCORE line from the visible comment if post_score is false.
Skips posting if the score is below min_risk_score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from github import Github, GithubException

from nodes.reviewer import ReviewResult
from nodes.fetcher import PRData


@dataclass
class PostResult:
    posted: bool
    comment_url: str | None
    reason: str             # why it was posted or skipped


def _strip_score_line(text: str) -> str:
    return re.sub(r"\nSCORE:\s*\d+\s*/\s*10\s*$", "", text, flags=re.IGNORECASE).strip()


def _format_comment(review: ReviewResult, pr: PRData, config: dict) -> str:
    review_cfg = config.get("review", {})
    post_score = review_cfg.get("post_score", True)

    body = review.raw

    header_parts = [
        "🤖 **AI Code Review** · powered by [ai-code-reviewer](https://github.com/nikhilsaiankilla/ai-code-reviewer)"]

    if post_score and review.score is not None:
        header_parts.append(f"📊 **Score: {review.score}/10**")
        # Remove the raw SCORE line from the body so it doesn't duplicate
        body = _strip_score_line(body)
    else:
        body = _strip_score_line(body)

    header = "  ·  ".join(header_parts)
    footer = "\n\n---\n*Self-hosted · ai-code-reviewer · MIT License*"

    return f"{header}\n\n{body}{footer}"


def post_comment(
    review: ReviewResult,
    pr: PRData,
    config: dict,
) -> PostResult:
    """
    Main function called by agent.py (Node 7).

    Args:
        review: ReviewResult from reviewer.py
        pr:     PRData from fetcher.py
        config: parsed config.yaml dict

    Returns:
        PostResult indicating whether the comment was posted
    """
    review_cfg = config.get("review", {})
    min_risk_score = review_cfg.get("min_risk_score", 0)

    if review.score is not None and review.score < min_risk_score:
        return PostResult(
            posted=False,
            comment_url=None,
            reason=f"Score {review.score}/10 is below min_risk_score {min_risk_score} — skipping comment",
        )

    comment_body = _format_comment(review, pr, config)

    try:
        g = Github(config["github_token"])
        repo = g.get_repo(pr.repo_name)
        pull = repo.get_pull(pr.pr_number)
        comment = pull.create_issue_comment(comment_body)
    except GithubException as e:
        raise RuntimeError(
            f"Failed to post comment on PR #{pr.pr_number}: {e.data}"
        ) from e

    return PostResult(
        posted=True,
        comment_url=comment.html_url,
        reason="Review posted successfully",
    )
