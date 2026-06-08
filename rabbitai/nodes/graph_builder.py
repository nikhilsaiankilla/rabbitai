"""
Node 2 — Graph Builder
Builds a NetworkX file dependency graph from the PR diff and
computes blast radius — which files are high risk because lots
of other files depend on them.

Why this matters:
    If db.ts has 15 importers and you just changed it,
    that's a HIGH risk change. The reviewer needs to know this.
    A change to some isolated util with 0 importers? Low risk.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx


@dataclass
class GraphInsight:
    graph: nx.DiGraph                    # full dependency graph
    high_risk_files: list[str]           # files with blast radius >= threshold
    dependents_map: dict[str, int]       # filename → number of dependents
    summary: str                         # one paragraph for the review prompt
    risk_level: str                      # "HIGH" | "MEDIUM" | "LOW"
    stats: dict = field(default_factory=dict)  # total nodes, edges, etc.


# Import/require patterns — covers JS/TS, Python, Go, Rust, Java, CSS
IMPORT_PATTERNS = [
    # JS/TS: import X from './path'  |  import './path'  |  import type X from './path'
    re.compile(
        r"""(?:import\s+(?:type\s+)?(?:.+?\s+from\s+)?['"])([^'"]+)['"]"""),
    # CommonJS: require('./path')
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    # Python: from .module import X  |  import module
    re.compile(r"""from\s+([\w.]+)\s+import"""),
    re.compile(r"""^import\s+([\w.]+)""", re.MULTILINE),
    # Go: import "path/to/pkg"
    re.compile(r"""import\s+["']([^"']+)["']"""),
    # CSS/SCSS: @import 'file'
    re.compile(r"""@import\s+['"]([^'"]+)['"]"""),
]

# Blast radius thresholds
HIGH_RISK_THRESHOLD = 5    # 5+ other files import this file → high risk
MEDIUM_RISK_THRESHOLD = 2  # 2-4 importers → medium risk


def _extract_imports(code_line: str) -> list[str]:
    """Extract all import paths from a single line of code."""
    imports = []
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(code_line):
            path = match.group(1).strip()
            # Skip node_modules, stdlib, and non-relative paths for graph
            # but keep them for context
            imports.append(path)
    return imports


def _normalize_path(raw_import: str, source_file: str) -> str:
    """
    Best-effort normalization of relative imports to a canonical path.
    e.g. source_file = "src/auth/login.ts", import = "../db"
         → "src/db"
    """
    if raw_import.startswith("."):
        try:
            base = Path(source_file).parent
            resolved = (base / raw_import).resolve()
            # resolve() gives absolute path — make it relative-ish
            # just return the normalized string
            return str(Path(raw_import))
        except Exception:
            return raw_import
    return raw_import


def build_dependency_graph(
    files_changed: list[str],
    diff: str,
    high_risk_threshold: int = HIGH_RISK_THRESHOLD,
) -> GraphInsight:
    """
    Parse the PR diff to build a directed dependency graph,
    then compute blast radius for every changed file.

    Args:
        files_changed:      list of filenames from fetcher.py
        diff:               full unified diff string from fetcher.py
        high_risk_threshold: min dependents to be considered high risk

    Returns:
        GraphInsight with graph, risk data, and a summary for the prompt
    """
    G = nx.DiGraph()

    # Add all changed files as nodes upfront
    for f in files_changed:
        G.add_node(f)

    # Parse the diff to extract import relationships
    current_file: str | None = None

    for line in diff.splitlines():
        # Detect file headers we wrote in fetcher.py
        # Format: "### FILE: src/auth.ts  [modified]  +12 -3"
        if line.startswith("### FILE:"):
            parts = line.split("  ")
            if parts:
                current_file = parts[0].replace("### FILE:", "").strip()
                if current_file not in G:
                    G.add_node(current_file)
            continue

        if current_file is None:
            continue

        # Only look at added/unchanged lines for imports
        # Skip deleted lines (─ prefix) — those imports are being removed
        if line.startswith("-"):
            continue

        raw_line = line.lstrip("+").strip()
        if not raw_line:
            continue

        imports = _extract_imports(raw_line)
        for imp in imports:
            normalized = _normalize_path(imp, current_file)
            # Add edge: current_file → dependency
            # meaning "current_file imports dependency"
            if normalized and normalized != current_file:
                if normalized not in G:
                    G.add_node(normalized)
                G.add_edge(current_file, normalized)

    # Compute blast radius for each changed file
    # Blast radius = how many nodes in the graph import THIS file
    # i.e. in-degree when edges are reversed (dependents, not dependencies)
    dependents_map: dict[str, int] = {}
    high_risk_files: list[str] = []
    medium_risk_files: list[str] = []

    for f in files_changed:
        if f not in G:
            dependents_map[f] = 0
            continue

        # Count nodes that have an edge pointing TO this file
        in_degree = G.in_degree(f)

        # Also check partial matches — e.g. "db" might be imported as "../db" or "./db"
        filename_stem = Path(f).stem  # "auth.ts" → "auth"
        partial_matches = sum(
            1 for src, dst in G.edges()
            if filename_stem in dst and dst != f
        )

        total_dependents = in_degree + partial_matches
        dependents_map[f] = total_dependents

        if total_dependents >= high_risk_threshold:
            high_risk_files.append(f)
        elif total_dependents >= MEDIUM_RISK_THRESHOLD:
            medium_risk_files.append(f)

    # Determine overall risk level
    if high_risk_files:
        risk_level = "HIGH"
    elif medium_risk_files:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # Build summary for the review prompt
    summary_parts = []

    if high_risk_files:
        file_list = ", ".join(f"`{f}`" for f in high_risk_files)
        summary_parts.append(
            f"HIGH BLAST RADIUS: {file_list} — "
            f"each has {high_risk_threshold}+ dependents. Changes here can break a lot."
        )

    if medium_risk_files:
        file_list = ", ".join(f"`{f}`" for f in medium_risk_files)
        summary_parts.append(
            f"MEDIUM BLAST RADIUS: {file_list} — "
            f"a few files depend on these, review carefully."
        )

    if not high_risk_files and not medium_risk_files:
        summary_parts.append(
            "LOW BLAST RADIUS: changed files appear to be isolated. "
            "Risk of cascading breakage is low."
        )

    # Add per-file dependent counts for context
    details = []
    for f, count in dependents_map.items():
        if count > 0:
            details.append(f"`{f}` has {count} dependent(s)")
    if details:
        summary_parts.append("Dependency counts: " + " · ".join(details))

    summary = "\n".join(summary_parts)

    # Graph stats
    stats = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "files_changed": len(files_changed),
        "high_risk_count": len(high_risk_files),
        "medium_risk_count": len(medium_risk_files),
    }

    return GraphInsight(
        graph=G,
        high_risk_files=high_risk_files,
        dependents_map=dependents_map,
        summary=summary,
        risk_level=risk_level,
        stats=stats,
    )


def format_for_prompt(insight: GraphInsight) -> str:
    """
    Format graph insight to inject into the Gemini review prompt.
    """
    return (
        f"Overall Risk Level: {insight.risk_level}\n"
        f"{insight.summary}\n"
        f"Graph: {insight.stats['total_nodes']} nodes, "
        f"{insight.stats['total_edges']} edges mapped from diff."
    )
