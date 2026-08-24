from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.release_factory.version import (
    ReleaseVersionAuthority,
    resolve_release_version_authority,
)
from project_pipeline.release_hardening.disposable_rehearsal import FIXED_ZIP_TIMESTAMP

MIXED_HEAD = "MIXED_HEAD"
ARTIFACT_KINDS = (
    "wheel",
    "sdist",
    "source_archive",
    "windows_executable",
    "windows_installer",
)
_SIDECAR_NAME = "candidate.json"


class BoundArtifact(ContractModel):
    kind: str
    name: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    source_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_tree: str = Field(pattern=r"^[a-f0-9]{40}$")
    bound: bool = True


class ReleaseBundle(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    cache_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: ReleaseVersionAuthority
    artifacts: tuple[BoundArtifact, ...]
    output_dir: str
    resumable: bool = False
    desktop_bound: bool


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_zip(entries: dict[str, bytes], archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    temporary.replace(archive_path)


def write_fixture_artifacts(
    dest: Path,
    *,
    version: ReleaseVersionAuthority,
    desktop_executable: bytes | None = None,
    desktop_installer: bytes | None = None,
) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    wheel_name = f"project_pipeline-{version.bundle_version}-py3-none-any.whl"
    sdist_name = f"project_pipeline-{version.bundle_version}.tar.zip"
    source_name = f"project-pipeline-{version.source_sha[:12]}.zip"
    identity = (
        f"Name: project-pipeline\nVersion: {version.bundle_version}\n"
        f"Source-SHA: {version.source_sha}\nSource-Tree: {version.source_tree}\n"
    )
    wheel = dest / wheel_name
    _write_zip(
        {
            f"project_pipeline-{version.bundle_version}.dist-info/METADATA": identity.encode(),
            "project_pipeline/__init__.py": f'__version__ = "{version.bundle_version}"\n'.encode(),
        },
        wheel,
    )
    sdist = dest / sdist_name
    _write_zip(
        {"PKG-INFO": identity.encode(), "pyproject.toml": b'[project]\nname="project-pipeline"\n'},
        sdist,
    )
    source = dest / source_name
    _write_zip(
        {
            "README.md": b"release candidate source archive\n",
            "VERSION": f"{version.bundle_version}\n".encode(),
            "SOURCE_SHA": f"{version.source_sha}\n".encode(),
            "SOURCE_TREE": f"{version.source_tree}\n".encode(),
        },
        source,
    )
    paths = {"wheel": wheel, "sdist": sdist, "source_archive": source}
    if desktop_executable is not None:
        exe = dest / f"ProjectPipeline_{version.desktop_version}_x64.exe"
        exe.write_bytes(desktop_executable)
        paths["windows_executable"] = exe
    if desktop_installer is not None:
        installer = dest / f"ProjectPipeline_{version.desktop_version}_x64-setup.exe"
        installer.write_bytes(desktop_installer)
        paths["windows_installer"] = installer
    return paths


def _write_source_fixture_archive(dest: Path, *, version: ReleaseVersionAuthority) -> Path:
    source_name = f"project-pipeline-{version.source_sha[:12]}.zip"
    source = dest / source_name
    _write_zip(
        {
            "README.md": b"release candidate source archive\n",
            "VERSION": f"{version.bundle_version}\n".encode(),
            "SOURCE_SHA": f"{version.source_sha}\n".encode(),
            "SOURCE_TREE": f"{version.source_tree}\n".encode(),
        },
        source,
    )
    return source


def _git_archive(root: Path, dest: Path, *, source_sha: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "archive",
            "--format=zip",
            f"--prefix=project-pipeline-{source_sha[:12]}/",
            "-o",
            str(dest),
            source_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0 or not dest.is_file():
        raise ValueError("git archive failed for the exact candidate SHA")
    return dest


def _build_python_distributions(root: Path, dest: Path) -> dict[str, Path]:
    for stale in (*dest.glob("*.whl"), *dest.glob("*.tar.gz")):
        stale.unlink(missing_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--sdist",
            "--outdir",
            str(dest),
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        cwd=str(root),
    )
    if completed.returncode != 0:
        raise ValueError("python distribution build failed for release candidate")
    wheels = sorted(path for path in dest.glob("*.whl") if path.is_file())
    sdists = sorted(path for path in dest.glob("*.tar.gz") if path.is_file())
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("release candidate requires exactly one wheel and one sdist")
    return {"wheel": wheels[0], "sdist": sdists[0]}


def _sidecar_path(artifact: Path) -> Path:
    return artifact.with_suffix(artifact.suffix + ".candidate.json")


def _write_sidecar(artifact: Path, bound: BoundArtifact) -> None:
    _sidecar_path(artifact).write_text(
        json.dumps(bound.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_sidecar(artifact: Path) -> BoundArtifact | None:
    path = _sidecar_path(artifact)
    if not path.is_file():
        return None
    return BoundArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def artifact_sha256s(bundle: ReleaseBundle) -> dict[str, str]:
    return {item.name: item.sha256 for item in bundle.artifacts if item.bound}


def build_release_bundle(
    root: Path,
    output_dir: Path,
    *,
    desktop_artifact_dir: Path | None = None,
    use_git_archive: bool = True,
    fixture_desktop: bool = False,
) -> ReleaseBundle:
    root = root.resolve()
    version = resolve_release_version_authority(root)
    cache_key = hashlib.sha256(
        f"{version.source_sha}:{version.source_tree}:{version.bundle_version}".encode()
    ).hexdigest()
    dest = output_dir.resolve() / cache_key
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / _SIDECAR_NAME
    if manifest_path.is_file():
        existing = ReleaseBundle.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        if existing.cache_key == cache_key and all(
            (dest / item.name).is_file() and _sha256_file(dest / item.name) == item.sha256
            for item in existing.artifacts
            if item.bound
        ):
            return existing.model_copy(update={"resumable": True, "output_dir": str(dest)})

    if fixture_desktop:
        # Test-only path for fixture desktop binaries; Python package artifacts stay real.
        paths = _build_python_distributions(root, dest)
        fixture_paths = write_fixture_artifacts(
            dest,
            version=version,
            desktop_executable=b"MZ-fixture-desktop-exe",
            desktop_installer=b"MZ-fixture-desktop-installer",
        )
        for key in ("windows_executable", "windows_installer"):
            if key in fixture_paths:
                paths[key] = fixture_paths[key]
    else:
        paths = _build_python_distributions(root, dest)
        if desktop_artifact_dir is not None:
            for kind, pattern in (
                ("windows_executable", "*.exe"),
                ("windows_installer", "*setup.exe"),
            ):
                matches = sorted(
                    path for path in desktop_artifact_dir.glob(pattern) if path.is_file()
                )
                if kind == "windows_executable":
                    matches = [path for path in matches if "setup" not in path.name.lower()]
                if len(matches) != 1:
                    raise ValueError(
                        f"desktop {kind} must resolve to exactly one file under --desktop-dir"
                    )
                desktop_sidecar = _read_sidecar(matches[0])
                if desktop_sidecar is None:
                    raise ValueError(f"desktop {kind} is missing candidate identity provenance")
                if (
                    desktop_sidecar.kind != kind
                    or desktop_sidecar.source_sha != version.source_sha
                    or desktop_sidecar.source_tree != version.source_tree
                ):
                    raise ValueError(f"{MIXED_HEAD}: {matches[0].name} provenance differs")
                copied = dest / matches[0].name
                copied.write_bytes(matches[0].read_bytes())
                paths[kind] = copied

    if use_git_archive:
        archive = dest / f"project-pipeline-{version.source_sha[:12]}.zip"
        paths["source_archive"] = _git_archive(root, archive, source_sha=version.source_sha)
    else:
        paths["source_archive"] = _write_source_fixture_archive(dest, version=version)

    artifacts: list[BoundArtifact] = []
    for kind, path in paths.items():
        sidecar = _read_sidecar(path)
        digest = _sha256_file(path)
        bound = BoundArtifact(
            kind=kind,
            name=path.name,
            sha256=digest,
            size_bytes=path.stat().st_size,
            source_sha=version.source_sha,
            source_tree=version.source_tree,
        )
        if sidecar is not None and (
            sidecar.source_sha != version.source_sha or sidecar.source_tree != version.source_tree
        ):
            raise ValueError(f"{MIXED_HEAD}: {path.name} was built from a different SHA/tree")
        _write_sidecar(path, bound)
        artifacts.append(bound)

    missing_desktop = {"windows_executable", "windows_installer"} - {
        item.kind for item in artifacts
    }
    for kind in sorted(missing_desktop):
        artifacts.append(
            BoundArtifact(
                kind=kind,
                name=f"UNBOUND-{kind}",
                sha256="0" * 64,
                size_bytes=0,
                source_sha=version.source_sha,
                source_tree=version.source_tree,
                bound=False,
            )
        )

    bundle = ReleaseBundle(
        cache_key=cache_key,
        version=version,
        artifacts=tuple(artifacts),
        output_dir=str(dest),
        resumable=False,
        desktop_bound=not missing_desktop,
    )
    manifest_path.write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle
