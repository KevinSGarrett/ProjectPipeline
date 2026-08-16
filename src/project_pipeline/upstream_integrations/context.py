from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_pipeline.upstream_integrations.common import (
    CommandOutcome,
    CommandPlan,
    Runner,
    default_runner,
    executable_available,
    execute_plan,
)


@dataclass(slots=True)
class RepomixAdapter:
    executable: str = "repomix"
    runner: Runner = default_runner
    timeout_seconds: float = 300.0

    def available(self) -> bool:
        return executable_available(self.executable)

    def plan(
        self,
        root: Path,
        *,
        token_budget: int,
        include: tuple[str, ...] = (),
        ignore: tuple[str, ...] = (),
    ) -> CommandPlan:
        root = root.resolve()
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        argv = [
            self.executable,
            str(root),
            "--stdout",
            "--style",
            "json",
            "--compress",
            "--output-show-line-numbers",
            "--token-budget",
            str(token_budget),
        ]
        if include:
            argv.extend(["--include", ",".join(include)])
        if ignore:
            argv.extend(["--ignore", ",".join(ignore)])
        if "--no-security-check" in argv or "--remote-trust-config" in argv:
            raise ValueError("unsafe Repomix security override is forbidden")
        return CommandPlan(
            upstream_id="UPSTREAM-115",
            argv=tuple(argv),
            cwd=str(root),
            network_required=False,
            output_format="json",
            evidence_sources=(
                "yamadashy/repomix:website/client/src/en/guide/command-line-options.md",
            ),
        )

    def execute(self, plan: CommandPlan) -> CommandOutcome:
        return execute_plan(plan, runner=self.runner, timeout_seconds=self.timeout_seconds)


@dataclass(slots=True)
class MarkItDownAdapter:
    """Optional lightweight document normalizer with plugins disabled by default."""

    def available(self) -> bool:
        try:
            import markitdown  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, source: Path) -> str:
        source = source.resolve()
        if not source.is_file():
            raise ValueError("MarkItDown source must be a file")
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError("markitdown dependency is unavailable") from exc
        converter = MarkItDown(enable_plugins=False)
        result = converter.convert(source)
        text = getattr(result, "text_content", None)
        if not isinstance(text, str):
            raise RuntimeError("MarkItDown returned no text content")
        return text


@dataclass(slots=True)
class DoclingAdapter:
    """Optional structured document normalizer for richer document formats."""

    max_file_size: int = 64 * 1024 * 1024
    max_num_pages: int = 500

    def available(self) -> bool:
        try:
            import docling  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, source: Path) -> str:
        source = source.resolve()
        if not source.is_file():
            raise ValueError("Docling source must be a file")
        if source.stat().st_size > self.max_file_size:
            raise ValueError("document exceeds Docling adapter size policy")
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise RuntimeError("docling dependency is unavailable") from exc
        converter = DocumentConverter()
        result = converter.convert(
            source, max_num_pages=self.max_num_pages, max_file_size=self.max_file_size
        )
        document = getattr(result, "document", None)
        if document is None or not hasattr(document, "export_to_markdown"):
            raise RuntimeError("Docling returned no structured document")
        return str(document.export_to_markdown())
