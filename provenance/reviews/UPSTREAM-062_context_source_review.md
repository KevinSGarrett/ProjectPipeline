# UPSTREAM-062 — Microsoft MarkItDown Context Review

- Repository: `microsoft/markitdown`
- Inspected revision: `fd239d5d2be43d9b68329730206b9312c7d5a388`
- License: MIT
- Decision: `ADOPT_DEPENDENCY` through an optional, bounded document-normalization adapter.
- Project Pipeline path: `src/project_pipeline/upstream_integrations/context.py`

## Source-level findings

`packages/markitdown/src/markitdown/_markitdown.py` provides a common converter registry for text, HTML, Office documents, PDF, images, archives and related formats. Built-in converters are enabled by default while third-party plugins are opt-in through `enable_plugins`. Project Pipeline deliberately constructs `MarkItDown(enable_plugins=False)` so repository-controlled plugin entry points cannot silently become executable context-ingestion extensions.

The reviewed package metadata in `packages/markitdown/pyproject.toml` declares Python >=3.10 and the MIT license. The current adapter is optional and truthful: absence of the dependency reports unavailable rather than installing it or claiming live qualification.

## Adoption boundary

MarkItDown is the lightweight document-to-Markdown normalization path. Project Pipeline still owns context authority, source provenance, trust classification, freshness, secret handling, egress policy, coverage, content-addressed pack identity and delegation semantics.

## Evidence sources

- https://github.com/microsoft/markitdown/tree/fd239d5d2be43d9b68329730206b9312c7d5a388
- https://github.com/microsoft/markitdown/blob/fd239d5d2be43d9b68329730206b9312c7d5a388/packages/markitdown/src/markitdown/_markitdown.py
- https://github.com/microsoft/markitdown/blob/fd239d5d2be43d9b68329730206b9312c7d5a388/packages/markitdown/pyproject.toml
