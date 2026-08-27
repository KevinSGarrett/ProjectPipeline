from __future__ import annotations

from project_pipeline.release_factory.lifecycle import _find_archive


def test_find_archive_prefers_source_archive_over_portable_bundle(tmp_path) -> None:
    portable = tmp_path / "project-pipeline-command-center-portable.zip"
    source = tmp_path / "project-pipeline-f52d2ea442a0.zip"
    portable.write_bytes(b"portable")
    source.write_bytes(b"source")

    selected = _find_archive(tmp_path)

    assert selected == source
