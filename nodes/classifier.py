"""
Node 4 — Classifier
Figures out what KIND of change this PR is so the reviewer
can focus on the right things.

Change types:
    bug_fix   → focus on logic errors, edge cases, regressions
    feature   → focus on design, correctness, missing error handling
    refactor  → focus on behaviour parity, unintended side effects
    security  → focus hard on auth, injection, secrets, validation
    docs      → light review, just check accuracy
    chore     → deps/config changes, check for breaking changes
"""

import re
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    change_type: str        # one of the 6 types above
    confidence: str         # "high" | "medium" | "low"
    reason: str             # why we picked this type
    review_focus: list[str]  # what the reviewer should prioritize


# Keywords that signal each change type — checked against PR title first
TITLE_SIGNALS: dict[str, list[str]] = {
    "security": [
        "security", "auth", "cve", "vuln", "vulnerability",
        "sanitize", "xss", "csrf", "injection", "exploit", "owasp",
        "permission", "rbac", "jwt", "token", "secret", "password"
    ],
    "bug_fix": [
        "fix", "bug", "patch", "hotfix", "issue", "crash",
        "error", "broken", "regression", "revert", "solve"
    ],
    "refactor": [
        "refactor", "cleanup", "clean up", "restructure",
        "reorganize", "rename", "move", "extract", "simplify", "dry"
    ],
    "feature": [
        "feat", "feature", "add", "new", "implement", "introduce",
        "support", "enable", "create", "build"
    ],
    "docs": [
        "docs", "doc", "readme", "documentation", "comment",
        "changelog", "typo", "spelling", "wiki"
    ],
    "chore": [
        "chore", "deps", "dependency", "dependencies", "update",
        "bump", "upgrade", "ci", "cd", "lint", "format",
        "config", "settings", "env", "dockerfile", "workflow"
    ],
}

# What to focus the review on per change type
REVIEW_FOCUS_MAP: dict[str, list[str]] = {
    "security": [
        "injection vulnerabilities (SQL, XSS, command)",
        "exposed secrets or hardcoded credentials",
        "broken authentication or authorization logic",
        "missing input validation or sanitization",
        "insecure direct object references",
    ],
    "bug_fix": [
        "whether the fix actually solves the root cause",
        "edge cases the fix might miss",
        "regressions introduced by the change",
        "null / undefined handling",
        "off-by-one errors",
    ],
    "refactor": [
        "behaviour parity with the original code",
        "unintended side effects",
        "performance changes (better or worse)",
        "broken imports or references after moves",
    ],
    "feature": [
        "missing error handling",
        "input validation",
        "edge cases not covered",
        "design and API surface",
        "test coverage for new logic",
    ],
    "docs": [
        "factual accuracy",
        "code examples that are outdated or wrong",
        "missing steps or unclear instructions",
    ],
    "chore": [
        "breaking changes in dependency upgrades",
        "config values that could cause issues in prod",
        "CI/CD pipeline correctness",
    ],
}


def classify_change(title: str, diff: str) -> ClassificationResult:
    """
    Classify a PR into one of 6 change types.

    Strategy:
    1. Check title against keyword lists (most reliable signal)
    2. If no title match, scan the diff for code-level signals
    3. Fall back to "feature" if nothing matches

    Args:
        title: PR title string
        diff:  full unified diff string from fetcher.py

    Returns:
        ClassificationResult with type, confidence, reason, and review focus
    """
    title_lower = title.lower().strip()

    # ── Step 1: Title match (high confidence)
    # Security checked first — always highest priority
    for change_type, keywords in TITLE_SIGNALS.items():
        for kw in keywords:
            if kw in title_lower:
                return ClassificationResult(
                    change_type=change_type,
                    confidence="high",
                    reason=f'Title contains "{kw}"',
                    review_focus=REVIEW_FOCUS_MAP[change_type],
                )

    # Step 2: Diff-level signals (medium confidence)
    diff_lower = diff.lower()

    # Security signals in the actual code diff
    security_patterns = [
        r"\b(password|passwd|secret|api_key|apikey|token|credential)\b",
        r"\b(sql|query|execute|cursor\.execute)\b",
        r"\b(eval|exec|subprocess|os\.system)\b",
        r"\b(jwt|bearer|oauth|session|cookie)\b",
        r"\b(escape|sanitize|validate|whitelist|blacklist)\b",
    ]
    for pattern in security_patterns:
        if re.search(pattern, diff_lower):
            return ClassificationResult(
                change_type="security",
                confidence="medium",
                reason=f"Diff contains security-sensitive pattern: {pattern}",
                review_focus=REVIEW_FOCUS_MAP["security"],
            )

    # Bug fix signals in diff
    bug_patterns = [
        r"\b(try|catch|except|finally)\b",
        r"\b(null|none|undefined|nan)\b",
        r"\b(if\s+not|if\s+none|is\s+none|== null|=== null)\b",
        r"\b(index out|keyerror|typeerror|valueerror|attributeerror)\b",
    ]
    for pattern in bug_patterns:
        if re.search(pattern, diff_lower):
            return ClassificationResult(
                change_type="bug_fix",
                confidence="medium",
                reason=f"Diff contains bug-fix pattern: {pattern}",
                review_focus=REVIEW_FOCUS_MAP["bug_fix"],
            )

    # Refactor signals — lots of deletions relative to additions
    added_lines = diff.count("\n+")
    deleted_lines = diff.count("\n-")
    if deleted_lines > 0 and added_lines > 0:
        ratio = deleted_lines / added_lines
        if 0.7 <= ratio <= 1.4 and deleted_lines > 20:
            return ClassificationResult(
                change_type="refactor",
                confidence="medium",
                reason=f"High line churn ratio ({deleted_lines} deletions / {added_lines} additions) suggests refactor",
                review_focus=REVIEW_FOCUS_MAP["refactor"],
            )

    # Docs signals
    doc_file_patterns = [r"\.md$", r"\.txt$",
                         r"\.rst$", r"readme", r"changelog", r"license"]
    for pattern in doc_file_patterns:
        if re.search(pattern, diff_lower):
            return ClassificationResult(
                change_type="docs",
                confidence="medium",
                reason=f"Diff touches documentation files (pattern: {pattern})",
                review_focus=REVIEW_FOCUS_MAP["docs"],
            )

    # Step 3: Fallback (low confidence)
    return ClassificationResult(
        change_type="feature",
        confidence="low",
        reason="No strong signals found — defaulting to feature review",
        review_focus=REVIEW_FOCUS_MAP["feature"],
    )


def format_for_prompt(result: ClassificationResult) -> str:
    """
    Format the classification result to inject into the review prompt.
    """
    focus_lines = "\n".join(f"  - {f}" for f in result.review_focus)
    return (
        f"Change Type: {result.change_type.upper()} "
        f"(confidence: {result.confidence} — {result.reason})\n"
        f"Review Focus:\n{focus_lines}"
    )
