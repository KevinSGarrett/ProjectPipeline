from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from project_pipeline.domain import (
    CompiledRepositoryMap,
    RepositoryDiscovery,
    RepositoryMapEntry,
)


def _fingerprint(entries: tuple[RepositoryMapEntry, ...]) -> str:
    payload = json.dumps(
        [entry.model_dump(mode="json") for entry in entries],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compile_repository_map(discovery: RepositoryDiscovery) -> CompiledRepositoryMap:
    entries = tuple(
        RepositoryMapEntry(
            path=item.path,
            role=item.role,
            language=item.language,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
            symbols=item.symbols,
            dependencies=item.dependencies,
            tested_by=item.tested_by,
            owners=item.owners,
            change_relevance=item.change_relevance,
        )
        for item in discovery.files
    )
    top_level = Counter(
        Path(entry.path).parts[0] if len(Path(entry.path).parts) > 1 else "_root"
        for entry in entries
    )
    languages = Counter(entry.language for entry in entries if entry.language)
    roles = Counter(entry.role.value for entry in entries)
    return CompiledRepositoryMap(
        root_path=discovery.root_path,
        fingerprint=_fingerprint(entries),
        file_count=len(entries),
        total_bytes=sum(entry.size_bytes for entry in entries),
        top_level_counts=dict(sorted(top_level.items())),
        language_counts=dict(sorted(languages.items())),
        role_counts=dict(sorted(roles.items())),
        entries=entries,
    )
