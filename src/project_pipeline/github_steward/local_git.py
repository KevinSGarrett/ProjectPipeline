from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterable
from pathlib import Path

from project_pipeline.domain.github import (
    BranchGuardianDecision,
    BranchGuardianFinding,
    BranchRole,
    GitBranch,
    GitRepositorySnapshot,
    GitWorktree,
    GuardianFindingSeverity,
    WorktreeState,
    github_identifier,
)


class LocalGitError(RuntimeError):
    """Fail-closed repository stewardship error."""


def _slug_from_remote(url: str) -> str | None:
    value = url.strip()
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("git@github.com:"):
        return value.split(":", 1)[1]
    marker = "github.com/"
    if marker in value:
        return value.split(marker, 1)[1].strip("/")
    return None


class LocalGitRepository:
    """Safe fixed-command Git adapter. It never invokes a shell or discovered commands."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not (self.root / ".git").exists():
            # linked worktrees store .git as a file; git itself remains authoritative.
            probe = self._run("rev-parse", "--is-inside-work-tree", check=False)
            if probe.returncode != 0 or probe.stdout.strip() != "true":
                raise LocalGitError(f"not a Git work tree: {self.root}")

    def _run(
        self, *args: str, check: bool = True, timeout: float = 30
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            capture_output=True,
            shell=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise LocalGitError(result.stderr.strip() or f"git command failed: {args!r}")
        return result

    def repository_slug(self) -> str:
        remotes = self.remotes()
        for name in ("origin", "upstream"):
            if name in remotes:
                slug = _slug_from_remote(remotes[name])
                if slug:
                    return slug
        # Local fixtures and offline repositories still need a stable authority identity.
        digest = hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()[:12]
        return f"local/{self.root.name}-{digest}"

    def remotes(self) -> dict[str, str]:
        names = self._run("remote").stdout.splitlines()
        result: dict[str, str] = {}
        for name in names:
            name = name.strip()
            if not name:
                continue
            url = self._run("remote", "get-url", name, check=False)
            if url.returncode == 0 and url.stdout.strip():
                result[name] = url.stdout.strip()
        return dict(sorted(result.items()))

    def default_branch(self) -> str:
        symbolic = self._run(
            "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False
        )
        if symbolic.returncode == 0 and symbolic.stdout.strip().startswith("origin/"):
            return symbolic.stdout.strip().split("/", 1)[1]
        for candidate in ("main", "master"):
            if (
                self._run(
                    "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}", check=False
                ).returncode
                == 0
            ):
                return candidate
        current = self._run("branch", "--show-current").stdout.strip()
        if current:
            return current
        raise LocalGitError("unable to determine default branch")

    def status_paths(self) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        result = self._run("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
        staged: set[str] = set()
        unstaged: set[str] = set()
        untracked: set[str] = set()
        for record in result.split("\0"):
            if not record:
                continue
            if len(record) < 4:
                continue
            x, y = record[0], record[1]
            path = record[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if x == "?" and y == "?":
                untracked.add(path)
                continue
            if x not in {" ", "?"}:
                staged.add(path)
            if y not in {" ", "?"}:
                unstaged.add(path)
        return tuple(sorted(staged)), tuple(sorted(unstaged)), tuple(sorted(untracked))

    def snapshot(self) -> GitRepositorySnapshot:
        head = self._run("rev-parse", "HEAD").stdout.strip().lower()
        current = self._run("branch", "--show-current").stdout.strip() or None
        staged, unstaged, untracked = self.status_paths()
        slug = self.repository_slug()
        return GitRepositorySnapshot(
            repository_id=github_identifier("GHREP", slug, head),
            repository_slug=slug,
            root_path=str(self.root),
            default_branch=self.default_branch(),
            head_sha=head,
            current_branch=current,
            detached_head=current is None,
            dirty=bool(staged or unstaged or untracked),
            staged_paths=staged,
            unstaged_paths=unstaged,
            untracked_paths=untracked,
            remotes=self.remotes(),
        )

    def branches(self) -> tuple[GitBranch, ...]:
        default = self.default_branch()
        current = self._run("branch", "--show-current").stdout.strip() or None
        fmt = "%(refname:short)%00%(objectname)%00%(upstream:short)%00%(upstream:track,nobracket)"
        lines = self._run(
            "for-each-ref", "--sort=refname", f"--format={fmt}", "refs/heads"
        ).stdout.splitlines()
        result: list[GitBranch] = []
        for line in lines:
            parts = line.split("\0")
            if len(parts) < 4:
                continue
            name, sha, upstream, track = parts[:4]
            ahead = behind = 0
            for token in track.split(","):
                token = token.strip()
                if token.startswith("ahead "):
                    ahead = int(token.split()[-1])
                elif token.startswith("behind "):
                    behind = int(token.split()[-1])
            merged_probe = self._run("merge-base", "--is-ancestor", sha, default, check=False)
            role = BranchRole.DEFAULT if name == default else BranchRole.FEATURE
            if name.startswith("release/"):
                role = BranchRole.RELEASE
            elif name.startswith("hotfix/"):
                role = BranchRole.HOTFIX
            result.append(
                GitBranch(
                    branch_id=github_identifier("GHBR", self.repository_slug(), name, sha),
                    name=name,
                    sha=sha.lower(),
                    role=role,
                    is_default=name == default,
                    is_current=name == current,
                    upstream=upstream or None,
                    ahead=ahead,
                    behind=behind,
                    merged_into_default=(merged_probe.returncode == 0),
                )
            )
        return tuple(result)

    def worktrees(self) -> tuple[GitWorktree, ...]:
        text = self._run("worktree", "list", "--porcelain").stdout
        entries: list[dict[str, str | bool]] = []
        current: dict[str, str | bool] = {}
        for raw in [*text.splitlines(), ""]:
            line = raw.strip()
            if not line:
                if current:
                    entries.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key in {"detached", "bare", "prunable", "locked"}:
                current[key] = value or True
            else:
                current[key] = value
        result: list[GitWorktree] = []
        for item in entries:
            path = str(item.get("worktree", ""))
            head = str(item.get("HEAD", ""))
            branch_ref = str(item.get("branch", ""))
            branch = branch_ref.removeprefix("refs/heads/") if branch_ref else None
            worktree_path = Path(path)
            state = WorktreeState.MISSING if not worktree_path.exists() else WorktreeState.CLEAN
            if bool(item.get("detached")):
                state = WorktreeState.DETACHED
            elif worktree_path.exists():
                probe = subprocess.run(
                    ["git", "-C", path, "status", "--porcelain"],
                    text=True,
                    capture_output=True,
                    shell=False,
                    timeout=30,
                )
                if probe.returncode == 0 and probe.stdout.strip():
                    state = WorktreeState.DIRTY
            result.append(
                GitWorktree(
                    worktree_id=github_identifier("GHWT", self.repository_slug(), path, head),
                    path=path,
                    head_sha=head.lower(),
                    branch=branch,
                    state=state,
                    prunable=bool(item.get("prunable")),
                    locked=bool(item.get("locked")),
                    lock_reason=str(item.get("locked"))
                    if isinstance(item.get("locked"), str)
                    else None,
                )
            )
        return tuple(result)

    def create_branch(
        self, branch: str, start_point: str, *, apply: bool = False
    ) -> dict[str, str | bool]:
        if not branch.strip() or branch.startswith("-"):
            raise LocalGitError("invalid branch name")
        check = self._run("check-ref-format", "--branch", branch, check=False)
        if check.returncode != 0:
            raise LocalGitError("invalid branch name")
        if not apply:
            return {
                "mode": "DRY_RUN",
                "branch": branch,
                "start_point": start_point,
                "applied": False,
            }
        self._run("branch", branch, start_point)
        return {"mode": "APPLY", "branch": branch, "start_point": start_point, "applied": True}

    def publish_branch(
        self, branch: str, *, remote: str = "origin", apply: bool = False
    ) -> dict[str, str | bool]:
        name = branch.strip()
        protected = {self.default_branch(), "main", "master", "HEAD"}
        if not name or name.startswith("-") or name in protected:
            raise LocalGitError("cannot publish a protected, symbolic, or invalid branch")
        check = self._run("check-ref-format", "--branch", name, check=False)
        if check.returncode != 0:
            raise LocalGitError("invalid branch name")
        sha = self._run("rev-parse", name).stdout.strip().lower()
        tree = self._run("rev-parse", f"{name}^{{tree}}").stdout.strip().lower()
        spec = f"refs/heads/{name}:refs/heads/{name}"
        payload = {
            "remote": remote,
            "branch": name,
            "sha": sha,
            "tree": tree,
            "refspec": spec,
            "force": False,
        }
        if not apply:
            return {"mode": "DRY_RUN", "applied": False, **payload}
        pushed = self._run("push", "-u", remote, spec, timeout=180)
        return {
            "mode": "APPLY",
            "applied": True,
            "stdout_tail": (pushed.stdout or "")[-512:],
            **payload,
        }

    def create_worktree(
        self, path: Path, branch: str, *, apply: bool = False
    ) -> dict[str, str | bool]:
        candidate = path.expanduser().resolve(strict=False)
        if candidate == self.root or self.root in candidate.parents:
            raise LocalGitError("worktree path must be outside the primary repository root")
        if not apply:
            return {"mode": "DRY_RUN", "path": str(candidate), "branch": branch, "applied": False}
        self._run("worktree", "add", str(candidate), branch)
        return {"mode": "APPLY", "path": str(candidate), "branch": branch, "applied": True}

    def remove_worktree(self, path: Path, *, apply: bool = False) -> dict[str, str | bool]:
        candidate = path.expanduser().resolve(strict=False)
        known = {Path(item.path).resolve(strict=False): item for item in self.worktrees()}
        item = known.get(candidate)
        if item is None:
            raise LocalGitError("worktree is not registered with this repository")
        if item.state is WorktreeState.DIRTY:
            raise LocalGitError("dirty worktree cannot be removed by Repository Steward")
        if item.branch == self.default_branch():
            raise LocalGitError("default-branch worktree cannot be removed by Repository Steward")
        if not apply:
            return {"mode": "DRY_RUN", "path": str(candidate), "applied": False}
        self._run("worktree", "remove", str(candidate))
        return {"mode": "APPLY", "path": str(candidate), "applied": True}


def evaluate_branch_guardian(
    snapshot: GitRepositorySnapshot, branches: Iterable[GitBranch], worktrees: Iterable[GitWorktree]
) -> BranchGuardianDecision:
    findings: list[BranchGuardianFinding] = []
    branch = snapshot.current_branch
    if snapshot.detached_head:
        findings.append(
            BranchGuardianFinding(
                code="DETACHED_HEAD",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Repository is in detached HEAD state.",
                remediation="Create or switch to a work-item branch before making changes.",
            )
        )
    if branch == snapshot.default_branch:
        findings.append(
            BranchGuardianFinding(
                code="DEFAULT_BRANCH_ACTIVE",
                severity=GuardianFindingSeverity.BLOCKING,
                message="The primary worktree is on the default branch.",
                remediation="Create a short-lived work-item branch before implementation.",
            )
        )
    if snapshot.dirty:
        findings.append(
            BranchGuardianFinding(
                code="WORKTREE_DIRTY",
                severity=GuardianFindingSeverity.WARNING,
                message="The primary worktree contains uncommitted changes.",
                remediation="Preserve, review, or commit scoped work before cleanup or branch switching.",
            )
        )
    current = next((item for item in branches if item.name == branch), None)
    if current and current.behind:
        findings.append(
            BranchGuardianFinding(
                code="BRANCH_BEHIND_UPSTREAM",
                severity=GuardianFindingSeverity.WARNING,
                message=f"Current branch is {current.behind} commit(s) behind its upstream.",
                remediation="Reconcile with the intended base before review or merge.",
            )
        )
    if current and current.ahead and not current.upstream:
        findings.append(
            BranchGuardianFinding(
                code="UNPUBLISHED_COMMITS",
                severity=GuardianFindingSeverity.WARNING,
                message="Current branch has no configured upstream.",
                remediation="Preserve the branch locally and explicitly authorize any remote publication.",
            )
        )
    if current and current.ahead and current.behind:
        findings.append(
            BranchGuardianFinding(
                code="REMOTE_DIVERGENCE",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Current branch has diverged from its upstream.",
                remediation="Reconcile unpublished and unmerged commits before cleanup or merge.",
            )
        )
    if current and current.merged_into_default is False and current.ahead:
        findings.append(
            BranchGuardianFinding(
                code="UNMERGED_CONTENT",
                severity=GuardianFindingSeverity.WARNING,
                message="Current branch contains commits that are not merged into the default branch.",
                remediation="Merge through the Merge Gate or preserve the unpublished work before deletion.",
            )
        )
    dirty_other = [
        item.path
        for item in worktrees
        if item.state is WorktreeState.DIRTY
        and Path(item.path).resolve(strict=False) != Path(snapshot.root_path).resolve(strict=False)
    ]
    if dirty_other:
        findings.append(
            BranchGuardianFinding(
                code="OTHER_DIRTY_WORKTREE",
                severity=GuardianFindingSeverity.WARNING,
                message="Another registered worktree contains uncommitted work.",
                remediation="Do not prune or delete that worktree until its work is preserved.",
            )
        )
    blocking = any(item.severity is GuardianFindingSeverity.BLOCKING for item in findings)
    dirty = snapshot.dirty or bool(dirty_other)
    return BranchGuardianDecision(
        repository_slug=snapshot.repository_slug,
        branch=branch,
        safe_for_work=not blocking,
        safe_for_cleanup=not blocking and not dirty,
        findings=tuple(findings),
    )


def evaluate_branch_deletion(
    *,
    branch: str,
    default_branch: str,
    worktree_branches: Iterable[str | None],
    dirty: bool,
    merged_into_default: bool | None,
    remote_only: bool,
    unpublished: bool = False,
) -> BranchGuardianDecision:
    findings: list[BranchGuardianFinding] = []
    if branch == default_branch:
        findings.append(
            BranchGuardianFinding(
                code="DEFAULT_BRANCH_ACTIVE",
                severity=GuardianFindingSeverity.BLOCKING,
                message="The default branch cannot be deleted.",
                remediation="Leave the protected default branch in place.",
            )
        )
    if branch in set(worktree_branches):
        findings.append(
            BranchGuardianFinding(
                code="ACTIVE_WORKTREE",
                severity=GuardianFindingSeverity.BLOCKING,
                message="A registered worktree still owns this branch.",
                remediation="Remove the worktree only after it is clean and preserved.",
            )
        )
    if dirty:
        findings.append(
            BranchGuardianFinding(
                code="WORKTREE_DIRTY",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Dirty or unpreserved work is still bound to this branch.",
                remediation="Preserve or restore the dirty paths before deletion.",
            )
        )
    if merged_into_default is False:
        findings.append(
            BranchGuardianFinding(
                code="UNMERGED_CONTENT",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Branch is not merged into the default branch.",
                remediation="Merge through the Merge Gate or archive the unique work first.",
            )
        )
    if unpublished:
        findings.append(
            BranchGuardianFinding(
                code="UNPUBLISHED_COMMITS",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Branch still has unpublished local commits.",
                remediation="Publish or archive the commits before deleting the branch.",
            )
        )
    if remote_only and findings:
        findings.append(
            BranchGuardianFinding(
                code="UNSAFE_DELETION",
                severity=GuardianFindingSeverity.BLOCKING,
                message="Remote deletion is denied while local safety predicates fail.",
                remediation="Do not delete the remote branch until every local predicate is green.",
            )
        )
    blocking = any(item.severity is GuardianFindingSeverity.BLOCKING for item in findings)
    return BranchGuardianDecision(
        repository_slug="local/deletion",
        branch=branch,
        safe_for_work=not blocking,
        safe_for_cleanup=not blocking,
        findings=tuple(findings),
    )
