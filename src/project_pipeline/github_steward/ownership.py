from __future__ import annotations

from pathlib import PurePosixPath

from project_pipeline.domain.github import (
    OwnershipKind,
    OwnershipState,
    ResourceOwnershipClaim,
    github_identifier,
)


def _normalize(resource: str) -> str:
    value = resource.replace("\\", "/").strip().strip("/")
    if (
        not value
        or value in {".", ".."}
        or any(part == ".." for part in PurePosixPath(value).parts)
    ):
        raise ValueError(
            "ownership resource must be a repository-relative path or stable resource name"
        )
    return value


def ownership_conflicts(left: ResourceOwnershipClaim, right: ResourceOwnershipClaim) -> bool:
    if left.state is not OwnershipState.ACTIVE or right.state is not OwnershipState.ACTIVE:
        return False
    if left.repository_slug != right.repository_slug or left.owner_task_id == right.owner_task_id:
        return False
    if left.resource_kind != right.resource_kind:
        return False
    a = _normalize(left.resource)
    b = _normalize(right.resource)
    if left.resource_kind in {OwnershipKind.FILE, OwnershipKind.DIRECTORY, OwnershipKind.SCHEMA}:
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")
    return a == b


class OwnershipRegistry:
    def __init__(self, claims: tuple[ResourceOwnershipClaim, ...] = ()) -> None:
        self._claims = list(claims)

    def active(self) -> tuple[ResourceOwnershipClaim, ...]:
        return tuple(item for item in self._claims if item.state is OwnershipState.ACTIVE)

    def acquire(
        self,
        *,
        repository_slug: str,
        resource_kind: OwnershipKind,
        resource: str,
        owner_task_id: str,
        workspace_id: str,
    ) -> ResourceOwnershipClaim:
        resource = _normalize(resource)
        candidate = ResourceOwnershipClaim(
            ownership_id=github_identifier(
                "GHOWN", repository_slug, resource_kind.value, resource, owner_task_id, workspace_id
            ),
            repository_slug=repository_slug,
            resource_kind=resource_kind,
            resource=resource,
            owner_task_id=owner_task_id,
            workspace_id=workspace_id,
        )
        for current in self.active():
            if ownership_conflicts(candidate, current):
                raise ValueError(
                    f"resource ownership conflict with {current.ownership_id}: {current.resource}"
                )
        self._claims.append(candidate)
        return candidate

    def release(self, ownership_id: str) -> ResourceOwnershipClaim:
        for index, item in enumerate(self._claims):
            if item.ownership_id == ownership_id:
                updated = item.model_copy(update={"state": OwnershipState.RELEASED})
                self._claims[index] = updated
                return updated
        raise KeyError(ownership_id)
