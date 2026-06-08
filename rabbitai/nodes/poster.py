"""
Node 7 — Poster
Formats the review result and posts it as a GitHub PR comment.
Posts a positive comment if score exceeds min_risk_score, full review otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from github import Auth, Github, GithubException

from rabbitai.nodes.fetcher import PRData
from rabbitai.nodes.reviewer import ReviewResult

LOGO = '<img src="https://raw.githubusercontent.com/nikhilsaiankilla/rabbitai/main/assets/rabbitai.png" width="20" height="20" alt="RabbitAI" style="vertical-align:middle;">'

FOOTER = (
    "\n\n---\n"
    "<sub>"
    "🐇 [RabbitAI](https://github.com/nikhilsaiankilla/rabbitai) "
    "&nbsp;·&nbsp; "
    "AI-powered code review "
    "&nbsp;·&nbsp; "
    "MIT License"
    "&nbsp;·&nbsp; "
    "[Nikhil](https://x.com/itzznikhilsai) "
    "</sub>"
)


@dataclass
class PostResult:
    posted: bool
    comment_url: str | None
    reason: str


def _strip_score_line(text: str) -> str:
    """Remove the raw SCORE line from the review body to avoid duplication in the header."""
    return re.sub(r"\nSCORE:\s*\d+\s*/\s*10\s*$", "", text, flags=re.IGNORECASE).strip()


def _format_comment(review: ReviewResult, config: dict) -> str:
    review_cfg = config.get("review", {})
    post_score = review_cfg.get("post_score", True)

    body = _strip_score_line(review.raw)

    if post_score and review.score is not None:
        header = f"{LOGO} **RabbitAI Code Review** &nbsp;·&nbsp; 📊 **{review.score}/10**"
    else:
        header = f"{LOGO} **RabbitAI Code Review**"

    return f"{header}\n\n{body}{FOOTER}"


def _format_positive_comment(review: ReviewResult) -> str:
    return (
        f"{LOGO} **RabbitAI Code Review** &nbsp;·&nbsp; 📊 **{review.score}/10**\n\n"
        f"**This PR looks solid!** No major issues detected.\n\n"
        f"> 🐇 RabbitAI reviewed this PR and found it in great shape. Nice work!\n\n"
        f"{FOOTER}"
    )


def _get_github_pull(config: dict, repo_name: str, pr_number: int):
    g = Github(auth=Auth.Token(config["github_token"]))
    repo = g.get_repo(repo_name)
    return repo.get_pull(pr_number)


def post_comment(
    review: ReviewResult,
    pr: PRData,
    config: dict,
) -> PostResult:
    """
    Main function called by agent.py (Node 7).
    Formats and posts the review as a GitHub PR comment.

    - Score above min_risk_score → posts a positive "looks great!" comment
    - Score below min_risk_score → posts full detailed review

    Args:
        review: ReviewResult from reviewer.py
        pr:     PRData from fetcher.py
        config: parsed config dict

    Returns:
        PostResult with posted status, comment URL, and reason
    """
    review_cfg = config.get("review", {})
    min_risk_score = review_cfg.get("min_risk_score", 0)

    try:
        pull = _get_github_pull(config, pr.repo_name, pr.pr_number)

        # High quality PR — post positive comment
        if review.score is not None and min_risk_score > 0 and review.score > min_risk_score:
            comment = pull.create_issue_comment(
                _format_positive_comment(review))
            return PostResult(
                posted=True,
                comment_url=comment.html_url,
                reason=f"Score {review.score}/10 — PR looks great, posted positive comment.",
            )

        # Low quality PR — post full review
        comment = pull.create_issue_comment(_format_comment(review, config))
        return PostResult(
            posted=True,
            comment_url=comment.html_url,
            reason="Review posted successfully.",
        )

    except GithubException as e:
        raise RuntimeError(
            f"Failed to post comment on PR #{pr.pr_number}: {e.data}"
        ) from e
