"""
Node 1 — Fetcher
Pulls the PR diff, metadata, and per-file patches from GitHub.
This is the raw input that every other node operates on.
"""

from dataclasses import dataclass
from github import Github, GithubException

from github import Auth


@dataclass
class PRData:
    repo_name: str
    pr_number: int
    title: str
    body: str
    author: str
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    diff: str                    # full unified diff as a single string
    files_changed: list[str]     # list of filenames touched
    # per-file: filename, status, additions, deletions, patch
    files_meta: list[dict]


def fetch_pr(github_token: str, repo_name: str, pr_number: int) -> PRData:
    """
    Fetch everything we need from a GitHub PR.

    Args:
        github_token: Personal access token or GITHUB_TOKEN from Actions
        repo_name:    owner/repo  e.g. "nikhilsaiankilla/rabbitai"
        pr_number:    integer PR number

    Returns:
        PRData with full diff + per-file metadata
    """
    try:
        g = Github(auth=Auth.Token(github_token))
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
    except GithubException as e:
        raise RuntimeError(
            f"GitHub API error fetching PR #{pr_number} from {repo_name}: {e.data}"
        ) from e

    files = list(pr.get_files())

    diff_parts: list[str] = []
    files_changed: list[str] = []
    files_meta: list[dict] = []

    for f in files:
        files_changed.append(f.filename)

        meta = {
            "filename": f.filename,
            "status": f.status,           # added | modified | removed | renamed
            "additions": f.additions,
            "deletions": f.deletions,
            "changes": f.changes,
            "patch": f.patch or "",       # None for binary files
        }
        files_meta.append(meta)

        if f.patch:
            # Format each file as a clear block so downstream nodes can
            # split by file easily if needed
            diff_parts.append(
                f"### FILE: {f.filename}  [{f.status}]  "
                f"+{f.additions} -{f.deletions}\n"
                f"{f.patch}"
            )
        else:
            # Binary or too-large file — note it but skip the patch
            diff_parts.append(
                f"### FILE: {f.filename}  [{f.status}]  (binary or no patch available)"
            )

    diff = "\n\n" + ("\n\n" + "─" * 60 + "\n\n").join(diff_parts)

    return PRData(
        repo_name=repo_name,
        pr_number=pr_number,
        title=pr.title,
        body=pr.body or "",
        author=pr.user.login,
        base_branch=pr.base.ref,
        head_branch=pr.head.ref,
        base_sha=pr.base.sha,
        head_sha=pr.head.sha,
        diff=diff,
        files_changed=files_changed,
        files_meta=files_meta,
    )


def diff_summary(pr_data: PRData) -> str:
    """
    Human-readable one-liner summary of what changed.
    Used as context header in the review prompt.
    """
    total_add = sum(f["additions"] for f in pr_data.files_meta)
    total_del = sum(f["deletions"] for f in pr_data.files_meta)
    n = len(pr_data.files_changed)

    return (
        f"PR #{pr_data.pr_number} by @{pr_data.author} · "
        f'"{pr_data.title}" · '
        f"{n} file{'s' if n != 1 else ''} changed · "
        f"+{total_add} -{total_del} lines · "
        f"{pr_data.base_branch} ← {pr_data.head_branch}"
    )
