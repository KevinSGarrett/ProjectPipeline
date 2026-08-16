from __future__ import annotations

import ast
import configparser
import fnmatch
import hashlib
import json
import os
import re
import stat
import tomllib
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from project_pipeline.domain import (
    DiscoveredFile,
    DiscoveredSymlink,
    DiscoveryArtifactKind,
    ProjectIntakeRequest,
    RepositoryDiscovery,
    RepositoryIdentity,
    RepositoryRole,
    VersionControlKind,
)


class DiscoveryError(RuntimeError):
    """Raised when a repository cannot be inspected within the configured safety boundary."""


IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".local",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "coverage",
        "dist",
        "build",
        "htmlcov",
        "node_modules",
        "target",
        "venv",
    }
)

TEXT_SUFFIXES = frozenset(
    {
        "",
        ".bat",
        ".cfg",
        ".conf",
        ".css",
        ".csv",
        ".env",
        ".example",
        ".go",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".kt",
        ".md",
        ".ps1",
        ".py",
        ".rb",
        ".rs",
        ".scss",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

LANGUAGE_BY_SUFFIX = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".php": "PHP",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
}

INSTRUCTION_BASENAMES = frozenset(
    {
        "agents.md",
        "claude.md",
        "codex.md",
        "gemini.md",
        "copilot-instructions.md",
        "instructions.md",
        "instruction.md",
    }
)
PLAN_DIRECTORY_NAMES = frozenset({"plan", "plans", "spec", "specs", "architecture"})
JIRA_DIRECTORY_NAMES = frozenset({"jira"})
REQUIREMENT_NAMES = frozenset(
    {
        "requirements.md",
        "requirements.json",
        "requirements.jsonl",
        "requirements.yaml",
        "requirements.yml",
    }
)
EVIDENCE_DIRECTORY_NAMES = frozenset({"evidence", "proof", "verification"})

_SECRET_REFERENCE = re.compile(r"(?:env|file)://[A-Za-z0-9_./\\-]+")
_PYTHON_IMPORT = re.compile(
    r"^(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_., ]+))", re.MULTILINE
)
_JS_IMPORT = re.compile(r"(?:from\s+|require\(|import\()\s*['\"]([^'\"]+)['\"]")
_RUST_USE = re.compile(r"^\s*(?:use|mod)\s+([A-Za-z0-9_:]+)", re.MULTILINE)
_JS_SYMBOL = re.compile(
    r"(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|const)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
)
_RUST_SYMBOL = re.compile(
    r"^\s*(?:pub\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _language(path: Path) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def _role(relative: str) -> DiscoveryArtifactKind:
    path = Path(relative)
    lower_parts = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    if name in INSTRUCTION_BASENAMES or any(
        part in {"instruction", "instructions"} for part in lower_parts
    ):
        return DiscoveryArtifactKind.INSTRUCTION
    if any(part in PLAN_DIRECTORY_NAMES for part in lower_parts):
        return DiscoveryArtifactKind.PLAN
    if any(part in JIRA_DIRECTORY_NAMES for part in lower_parts):
        return DiscoveryArtifactKind.JIRA
    if name in REQUIREMENT_NAMES or any(part == "requirements" for part in lower_parts):
        return DiscoveryArtifactKind.REQUIREMENT
    if any(part in EVIDENCE_DIRECTORY_NAMES for part in lower_parts):
        return DiscoveryArtifactKind.EVIDENCE
    if any(part in {"test", "tests", "spec", "specs"} for part in lower_parts) or name.startswith(
        "test_"
    ):
        return DiscoveryArtifactKind.TEST
    if relative.startswith(".github/workflows/") or name in {
        "azure-pipelines.yml",
        ".gitlab-ci.yml",
        "jenkinsfile",
    }:
        return DiscoveryArtifactKind.CI
    if name in {
        "cargo.toml",
        "go.mod",
        "makefile",
        "package.json",
        "pom.xml",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
    } or name.startswith("requirements"):
        return DiscoveryArtifactKind.BUILD
    if name in {
        "dockerfile",
        "compose.yml",
        "compose.yaml",
        "docker-compose.yml",
        "docker-compose.yaml",
    } or any(
        part in {"deploy", "deployment", "infra", "terraform", "kubernetes", "k8s"}
        for part in lower_parts
    ):
        return DiscoveryArtifactKind.DEPLOYMENT
    if name in {"readme.md", "contributing.md", "security.md", "license", "license.md"} or any(
        part == "docs" for part in lower_parts
    ):
        return DiscoveryArtifactKind.DOCUMENTATION
    if path.suffix.lower() in {".env", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml", ".json"}:
        return DiscoveryArtifactKind.CONFIGURATION
    if _language(path):
        return DiscoveryArtifactKind.SOURCE
    return DiscoveryArtifactKind.OTHER


def _read_text(path: Path, *, limit: int = 2_000_000) -> tuple[str | None, str | None]:
    try:
        size = path.stat().st_size
        if size > limit:
            return None, f"text inspection skipped above {limit} bytes"
        data = path.read_bytes()
        if b"\x00" in data:
            return None, "binary content not inspected"
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "non-UTF-8 content not inspected"
    except OSError as error:
        return None, f"text inspection failed: {type(error).__name__}"


def _python_metadata(text: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    diagnostics: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return (), (), (f"python syntax could not be parsed at line {error.lineno}",)
    symbols: set[str] = set()
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Import):
            dependencies.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            dependencies.add(node.module)
    return tuple(sorted(symbols)), tuple(sorted(dependencies)), tuple(diagnostics)


def _text_metadata(
    path: Path, text: str
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _python_metadata(text)
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return (
            tuple(sorted(set(_JS_SYMBOL.findall(text)))),
            tuple(sorted(set(_JS_IMPORT.findall(text)))),
            (),
        )
    if suffix == ".rs":
        return (
            tuple(sorted(set(_RUST_SYMBOL.findall(text)))),
            tuple(sorted(set(_RUST_USE.findall(text)))),
            (),
        )
    if suffix == ".go":
        symbols = tuple(
            sorted(
                set(re.findall(r"^\s*(?:func|type)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE))
            )
        )
        dependencies = tuple(sorted(set(re.findall(r'"([^"\n]+)"', text))))
        return symbols, dependencies, ()
    return (), (), ()


def _change_relevance(role: DiscoveryArtifactKind, path: str) -> tuple[str, ...]:
    relevance = {role.value.lower()}
    if role in {DiscoveryArtifactKind.BUILD, DiscoveryArtifactKind.CONFIGURATION}:
        relevance.add("dependency_or_runtime_configuration")
    if role is DiscoveryArtifactKind.CI:
        relevance.add("verification_pipeline")
    if role is DiscoveryArtifactKind.DEPLOYMENT:
        relevance.add("runtime_or_release")
    if path.startswith("src/") or path.startswith("apps/") or path.startswith("services/"):
        relevance.add("product_behavior")
    if path.startswith("tests/"):
        relevance.add("verification")
    return tuple(sorted(relevance))


def _load_codeowners(root: Path) -> tuple[tuple[str, tuple[str, ...]], ...]:
    candidates = (
        root / ".github" / "CODEOWNERS",
        root / "CODEOWNERS",
        root / "docs" / "CODEOWNERS",
    )
    for path in candidates:
        if not path.is_file():
            continue
        entries: list[tuple[str, tuple[str, ...]]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                entries.append((parts[0], tuple(parts[1:])))
        return tuple(entries)
    return ()


def _owners_for(path: str, entries: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
    owners: tuple[str, ...] = ()
    for pattern, candidate_owners in entries:
        normalized = pattern.lstrip("/")
        if normalized.endswith("/"):
            normalized += "*"
        if fnmatch.fnmatch(path, normalized) or fnmatch.fnmatch("/" + path, pattern):
            owners = candidate_owners
    return owners


def _tested_by(files: Iterable[str]) -> dict[str, tuple[str, ...]]:
    paths = sorted(files)
    tests = [path for path in paths if _role(path) is DiscoveryArtifactKind.TEST]
    result: dict[str, tuple[str, ...]] = {}
    for path in paths:
        if _role(path) is not DiscoveryArtifactKind.SOURCE:
            continue
        stem = Path(path).stem.lower()
        matches = [
            test for test in tests if stem in Path(test).stem.lower() or stem in test.lower()
        ]
        result[path] = tuple(sorted(matches))
    return result


def _read_git_identity(
    root: Path, canonical_url: str | None, *, nested: bool = False
) -> RepositoryIdentity:
    git_path = root / ".git"
    version_control = VersionControlKind.GIT if git_path.exists() else VersionControlKind.NONE
    branch: str | None = None
    revision: str | None = None
    observed_url = canonical_url
    if git_path.is_dir():
        head = git_path / "HEAD"
        if head.is_file():
            text = head.read_text(encoding="utf-8", errors="replace").strip()
            if text.startswith("ref: refs/heads/"):
                branch = text.removeprefix("ref: refs/heads/")
                ref = git_path / text.removeprefix("ref: ")
                if ref.is_file():
                    revision = ref.read_text(encoding="ascii", errors="ignore").strip() or None
            elif re.fullmatch(r"[a-fA-F0-9]{7,64}", text):
                revision = text
        config = git_path / "config"
        if observed_url is None and config.is_file():
            parser = configparser.ConfigParser()
            try:
                parser.read(config, encoding="utf-8")
                if parser.has_option('remote "origin"', "url"):
                    observed_url = parser.get('remote "origin"', "url")
            except configparser.Error:
                observed_url = canonical_url
    repository_id = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-") or "repository"
    return RepositoryIdentity(
        repository_id=repository_id,
        root_path="." if not nested else root.name,
        role=RepositoryRole.SUPPORTING if nested else RepositoryRole.PRIMARY,
        version_control=version_control,
        canonical_url=observed_url,
        default_branch=branch,
        head_revision=revision,
        nested=nested,
    )


def _discover_build_and_commands(
    root: Path, files: set[str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], list[str]]:
    build_systems: set[str] = set()
    test_commands: set[str] = set()
    deployments: set[str] = set()
    diagnostics: list[str] = []
    if "pyproject.toml" in files:
        build_systems.add("python:pyproject")
        test_commands.add("python -m pytest")
        try:
            tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            diagnostics.append(f"pyproject.toml is not parseable: {type(error).__name__}")
    if "requirements.txt" in files or any(path.startswith("requirements/") for path in files):
        build_systems.add("python:requirements")
    if "package.json" in files:
        build_systems.add("node:package-json")
        try:
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            if isinstance(scripts, dict):
                for name in ("test", "lint", "typecheck", "build"):
                    if name in scripts:
                        test_commands.add(f"npm run {name}")
        except (OSError, json.JSONDecodeError) as error:
            diagnostics.append(f"package.json is not parseable: {type(error).__name__}")
    if "Cargo.toml" in files:
        build_systems.add("rust:cargo")
        test_commands.add("cargo test")
    if "go.mod" in files:
        build_systems.add("go:modules")
        test_commands.add("go test ./...")
    if "Makefile" in files or "makefile" in files:
        build_systems.add("make")
    for path in files:
        name = Path(path).name.lower()
        lower = path.lower()
        if name == "dockerfile" or name.startswith("dockerfile."):
            deployments.add("docker")
        if name in {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"}:
            deployments.add("docker-compose")
        if lower.startswith(("infra/", "terraform/")) or path.endswith(".tf"):
            deployments.add("terraform")
        if lower.startswith(("k8s/", "kubernetes/")):
            deployments.add("kubernetes")
        if lower.startswith(".github/workflows/"):
            deployments.add("github-actions")
    return (
        tuple(sorted(build_systems)),
        tuple(sorted(test_commands)),
        tuple(sorted(deployments)),
        diagnostics,
    )


def discover_repository(request: ProjectIntakeRequest) -> RepositoryDiscovery:
    root = Path(request.target_root).expanduser().resolve(strict=False)
    if request.mode.value == "EXISTING_PROJECT" and not root.is_dir():
        raise DiscoveryError(f"existing project root is not a directory: {root}")
    if root.exists() and not root.is_dir():
        raise DiscoveryError(f"project target is not a directory: {root}")
    if root == Path(root.anchor):
        raise DiscoveryError("filesystem roots cannot be used as project targets")
    if not root.exists():
        primary = _read_git_identity(root, request.canonical_url)
        return RepositoryDiscovery(
            root_path=str(root),
            repositories=(primary,),
            files=(),
            total_bytes=0,
        )

    owners = _load_codeowners(root)
    provisional: list[dict[str, object]] = []
    symlinks: list[DiscoveredSymlink] = []
    boundary_violations: set[str] = set()
    diagnostics: set[str] = set()
    nested_roots: set[str] = set()
    total_bytes = 0
    file_count = 0
    secret_reference_count = 0

    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directory_names.sort(key=str.lower)
        file_names.sort(key=str.lower)
        retained: list[str] = []
        for name in directory_names:
            path = current_path / name
            relative = _relative(path, root)
            if path.is_symlink():
                target = path.resolve(strict=False)
                within = target == root or root in target.parents
                symlinks.append(
                    DiscoveredSymlink(
                        path=relative,
                        target=str(target),
                        target_within_root=within,
                    )
                )
                if not within:
                    boundary_violations.add(relative)
                continue
            if name in IGNORED_DIRECTORY_NAMES:
                continue
            if (path / ".git").exists():
                nested_roots.add(relative)
                if not request.allow_nested_repositories:
                    boundary_violations.add(f"nested-repository:{relative}")
                    continue
            retained.append(name)
        directory_names[:] = retained

        for name in file_names:
            path = current_path / name
            relative = _relative(path, root)
            try:
                mode = path.lstat().st_mode
            except OSError as error:
                diagnostics.add(f"cannot inspect {relative}: {type(error).__name__}")
                continue
            if stat.S_ISLNK(mode):
                target = path.resolve(strict=False)
                within = target == root or root in target.parents
                symlinks.append(
                    DiscoveredSymlink(
                        path=relative,
                        target=str(target),
                        target_within_root=within,
                    )
                )
                if not within:
                    boundary_violations.add(relative)
                continue
            if not stat.S_ISREG(mode):
                diagnostics.add(f"non-regular file skipped: {relative}")
                continue
            size = path.stat().st_size
            file_count += 1
            total_bytes += size
            if file_count > request.max_files:
                raise DiscoveryError(f"repository exceeds configured max_files={request.max_files}")
            if total_bytes > request.max_total_bytes:
                raise DiscoveryError(
                    f"repository exceeds configured max_total_bytes={request.max_total_bytes}"
                )
            digest = _sha256(path) if size <= request.max_hash_bytes_per_file else None
            file_diagnostics: list[str] = []
            if digest is None:
                file_diagnostics.append(
                    f"hash skipped above {request.max_hash_bytes_per_file} bytes"
                )
            symbols: tuple[str, ...] = ()
            dependencies: tuple[str, ...] = ()
            text: str | None = None
            if path.suffix.lower() in TEXT_SUFFIXES or not path.suffix:
                text, text_diagnostic = _read_text(path)
                if text_diagnostic:
                    file_diagnostics.append(text_diagnostic)
                if text is not None:
                    secret_reference_count += len(_SECRET_REFERENCE.findall(text))
                    symbols, dependencies, metadata_diagnostics = _text_metadata(path, text)
                    file_diagnostics.extend(metadata_diagnostics)
            provisional.append(
                {
                    "path": relative,
                    "size_bytes": size,
                    "sha256": digest,
                    "suffix": path.suffix.lower(),
                    "language": _language(path),
                    "role": _role(relative),
                    "symbols": symbols,
                    "dependencies": dependencies,
                    "owners": _owners_for(relative, owners),
                    "change_relevance": _change_relevance(_role(relative), relative),
                    "diagnostics": tuple(sorted(set(file_diagnostics))),
                }
            )

    all_paths = {str(item["path"]) for item in provisional}
    test_links = _tested_by(all_paths)
    files = tuple(
        DiscoveredFile.model_validate({**item, "tested_by": test_links.get(str(item["path"]), ())})
        for item in sorted(provisional, key=lambda item: str(item["path"]).lower())
    )
    build_systems, test_commands, deployment_surfaces, build_diagnostics = (
        _discover_build_and_commands(root, all_paths)
    )
    diagnostics.update(build_diagnostics)

    repositories: list[RepositoryIdentity] = [_read_git_identity(root, request.canonical_url)]
    for relative in sorted(nested_roots):
        nested_root = root / relative
        identity = _read_git_identity(nested_root, None, nested=True)
        identity = identity.model_copy(update={"root_path": relative})
        repositories.append(identity)

    def paths_for(role: DiscoveryArtifactKind) -> tuple[str, ...]:
        return tuple(sorted(item.path for item in files if item.role is role))

    return RepositoryDiscovery(
        root_path=str(root),
        repositories=tuple(repositories),
        files=files,
        symlinks=tuple(sorted(symlinks, key=lambda item: item.path)),
        instruction_paths=paths_for(DiscoveryArtifactKind.INSTRUCTION),
        plan_paths=paths_for(DiscoveryArtifactKind.PLAN),
        jira_paths=paths_for(DiscoveryArtifactKind.JIRA),
        requirement_paths=paths_for(DiscoveryArtifactKind.REQUIREMENT),
        evidence_paths=paths_for(DiscoveryArtifactKind.EVIDENCE),
        build_systems=build_systems,
        test_commands=test_commands,
        deployment_surfaces=deployment_surfaces,
        secret_reference_count=secret_reference_count,
        boundary_violations=tuple(sorted(boundary_violations)),
        diagnostics=tuple(sorted(diagnostics)),
        total_bytes=total_bytes,
        truncated=False,
    )


def discovery_summary(discovery: RepositoryDiscovery) -> dict[str, object]:
    return {
        "schema_version": discovery.schema_version,
        "root_path": discovery.root_path,
        "repository_count": len(discovery.repositories),
        "file_count": len(discovery.files),
        "total_bytes": discovery.total_bytes,
        "language_counts": dict(
            sorted(Counter(item.language for item in discovery.files if item.language).items())
        ),
        "role_counts": dict(sorted(Counter(item.role.value for item in discovery.files).items())),
        "instruction_count": len(discovery.instruction_paths),
        "plan_count": len(discovery.plan_paths),
        "jira_count": len(discovery.jira_paths),
        "requirement_count": len(discovery.requirement_paths),
        "evidence_count": len(discovery.evidence_paths),
        "boundary_violation_count": len(discovery.boundary_violations),
        "diagnostics": list(discovery.diagnostics),
    }
