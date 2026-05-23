"""
Node 7 — Poster
Formats the review result and posts it as a GitHub PR comment.
Skips posting if the PR score exceeds min_risk_score threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from github import Auth, Github, GithubException

from nodes.fetcher import PRData
from nodes.reviewer import ReviewResult


@dataclass
class PostResult:
    posted: bool
    comment_url: str | None
    reason: str


def _strip_score_line(text: str) -> str:
    """Remove the raw SCORE line from the review body to avoid duplication in the header."""
    return re.sub(r"\nSCORE:\s*\d+\s*/\s*10\s*$", "", text, flags=re.IGNORECASE).strip()


def _format_comment(review: ReviewResult, pr: PRData, config: dict) -> str:
    review_cfg = config.get("review", {})
    post_score = review_cfg.get("post_score", True)

    body = _strip_score_line(review.raw)

    # Header
    logo = "![RabbitAI](https://raw.githubusercontent.com/nikhilsaiankilla/rabbitai/main/assets/rabbitai.png)"
    title = "**RabbitAI Code Review**"

    if post_score and review.score is not None:
        score_badge = f"📊 **{review.score}/10**"
        header = f"{logo} {title} &nbsp;·&nbsp; {score_badge}"
    else:
        header = f"{logo} {title}"

    # Footer
    footer = (
        "\n\n---\n"
        "<sub>"
        "🐇 [RabbitAI](https://github.com/nikhilsaiankilla/rabbitai) "
        "&nbsp;·&nbsp; "
        "AI-powered code review "
        "&nbsp;·&nbsp; "
        "MIT License"
        "</sub>"
    )

    return f"{header}\n\n{body}{footer}"


def post_comment(
    review: ReviewResult,
    pr: PRData,
    config: dict,
) -> PostResult:
    """
    Main function called by agent.py (Node 7).
    Formats and posts the review as a GitHub PR comment.

    Skips posting if the PR score is above min_risk_score
    (high score = good PR, no comment needed).

    Args:
        review: ReviewResult from reviewer.py
        pr:     PRData from fetcher.py
        config: parsed config.yaml dict

    Returns:
        PostResult with posted status, comment URL, and reason
    """
    review_cfg = config.get("review", {})
    min_risk_score = review_cfg.get("min_risk_score", 0)

    # Skip if PR is high quality and below the risk threshold
    if review.score is not None and min_risk_score > 0 and review.score > min_risk_score:
        return PostResult(
            posted=False,
            comment_url=None,
            reason=(
                f"Score {review.score}/10 exceeds min_risk_score threshold of "
                f"{min_risk_score} — PR looks good, skipping comment."
            ),
        )

    comment_body = _format_comment(review, pr, config)

    try:
        g = Github(auth=Auth.Token(config["github_token"]))
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
        reason="Review posted successfully.",
    )
