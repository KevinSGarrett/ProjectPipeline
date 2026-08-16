from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from project_pipeline.ports import ArtifactReference


class ArtifactIntegrityError(RuntimeError):
    """Raised when immutable artifact bytes do not match their identity."""


class LocalContentAddressedStore:
    """Atomic SHA-256 content-addressed byte storage for local-first operation."""

    def __init__(self, root: Path, *, create: bool = True) -> None:
        self.root = root.resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Invalid SHA-256 digest")
        return self.root / digest[:2] / digest[2:4] / digest

    def put(
        self, content: bytes, media_type: str = "application/octet-stream"
    ) -> ArtifactReference:
        digest = self._digest(content)
        destination = self._path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            observed = destination.read_bytes()
            if observed != content:
                raise ArtifactIntegrityError(f"Existing bytes do not match digest {digest}")
        else:
            descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=destination.parent)
            temporary_path = Path(temporary)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if destination.exists():
                    temporary_path.unlink(missing_ok=True)
                else:
                    os.replace(temporary_path, destination)
            finally:
                temporary_path.unlink(missing_ok=True)
        return ArtifactReference("sha256", digest, len(content), media_type)

    def get(self, reference: ArtifactReference) -> bytes:
        if reference.algorithm != "sha256":
            raise ValueError(f"Unsupported digest algorithm: {reference.algorithm}")
        content = self._path(reference.digest).read_bytes()
        if len(content) != reference.size_bytes or self._digest(content) != reference.digest:
            raise ArtifactIntegrityError(f"Artifact verification failed: {reference.digest}")
        return content

    def verify(self, reference: ArtifactReference) -> bool:
        try:
            self.get(reference)
        except (FileNotFoundError, ArtifactIntegrityError, ValueError):
            return False
        return True
