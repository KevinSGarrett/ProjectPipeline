from __future__ import annotations

import subprocess
from pathlib import Path

from project_pipeline.domain.github import ConsolidationProof, github_identifier
from project_pipeline.github_steward.errors import GitHubStewardError


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        shell=False,
        timeout=30,
    )


def _rev_parse(root: Path, rev: str, suffix: str = "^{commit}") -> str:
    result = _run(root, "rev-parse", "--verify", f"{rev}{suffix}")
    if result.returncode != 0:
        raise GitHubStewardError(result.stderr.strip() or f"unable to resolve {rev}")
    return result.stdout.strip().lower()


def prove_consolidation(
    root: Path,
    *,
    repository_slug: str,
    consolidated_head: str,
    component_heads: tuple[str, ...],
    expected_tree: str | None = None,
) -> ConsolidationProof:
    resolved_head = _rev_parse(root, consolidated_head)
    resolved_tree = _rev_parse(root, consolidated_head, "^{tree}")
    ancestor_failures: list[str] = []
    for component in component_heads:
        sha = _rev_parse(root, component)
        probe = _run(root, "merge-base", "--is-ancestor", sha, resolved_head)
        if probe.returncode != 0:
            ancestor_failures.append(sha)
    tree_mismatches: list[str] = []
    if expected_tree is None:
        tree_mismatches.append("expected_tree_missing")
    elif expected_tree.lower() != resolved_tree:
        tree_mismatches.append(expected_tree.lower())
    eligible = not ancestor_failures and not tree_mismatches
    return ConsolidationProof(
        proof_id=github_identifier("GHCON", repository_slug, resolved_head, resolved_tree),
        repository_slug=repository_slug,
        consolidated_head=resolved_head,
        consolidated_tree=resolved_tree,
        component_heads=tuple(item.lower() for item in component_heads),
        ancestor_failures=tuple(ancestor_failures),
        tree_mismatches=tuple(tree_mismatches),
        eligible_to_supersede=eligible,
    )
