from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from project_pipeline.configuration.models import SecretReference


class SecretResolutionError(RuntimeError):
    """Raised when an explicitly requested secret reference cannot be resolved safely."""


class SecretResolver:
    """Resolve env:// and repository-confined file:// references on explicit demand."""

    def __init__(self, root: Path, environment: Mapping[str, str] | None = None) -> None:
        self.root = root.resolve()
        self.environment = os.environ if environment is None else environment

    def resolve(self, reference: SecretReference) -> str:
        if reference.scheme == "env":
            value = self.environment.get(reference.target)
            if value is None:
                raise SecretResolutionError(
                    f"required environment secret is unavailable: {reference.reference}"
                )
            return value
        candidate = self.root / reference.target
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise SecretResolutionError(
                f"file secret escapes the project root: {reference.reference}"
            ) from error
        try:
            value = resolved.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise SecretResolutionError(
                f"file secret is unavailable: {reference.reference}"
            ) from error
        if not value:
            raise SecretResolutionError(f"file secret is empty: {reference.reference}")
        return value
