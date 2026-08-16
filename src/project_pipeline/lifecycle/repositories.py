from __future__ import annotations

from project_pipeline.domain.lifecycle import CrossRepositoryChangeSet, RepositoryBinding


class MultiRepositoryCoordinator:
    def __init__(self, repositories: tuple[RepositoryBinding, ...]) -> None:
        self.repositories = {r.repository_id: r for r in repositories}
        if len(self.repositories) != len(repositories):
            raise ValueError("duplicate repository_id")
        unknown = {d for r in repositories for d in r.dependencies if d not in self.repositories}
        if unknown:
            raise ValueError(f"unknown repository dependencies: {sorted(unknown)}")

    def validate_change_set(self, change: CrossRepositoryChangeSet) -> dict[str, object]:
        unknown = set(change.repository_changes) - set(self.repositories)
        if unknown:
            raise ValueError(f"change set references unknown repositories: {sorted(unknown)}")
        positions = {repo: i for i, repo in enumerate(change.merge_order)}
        violations = []
        for repo_id in change.merge_order:
            for dependency in self.repositories[repo_id].dependencies:
                if dependency in positions and positions[dependency] > positions[repo_id]:
                    violations.append(f"{repo_id} must merge after dependency {dependency}")
        return {
            "change_set_id": change.change_set_id,
            "shared_change_identity": change.shared_change_identity,
            "repository_count": len(change.repository_changes),
            "merge_order_valid": not violations,
            "violations": violations,
            "per_repository_authority_preserved": True,
            "external_mutation_performed": False,
        }
