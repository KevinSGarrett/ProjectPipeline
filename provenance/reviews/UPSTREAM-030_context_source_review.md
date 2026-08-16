# UPSTREAM-030 — Docling Context Review

- Repository: `docling-project/docling`
- Inspected revision: `61d76f1ff3f8428065465889f7b4577da7df704c`
- License: MIT
- Reviewed package version: `docling-slim 2.120.1`
- Decision: `ADOPT_DEPENDENCY` through an optional structured-document adapter.
- Project Pipeline path: `src/project_pipeline/upstream_integrations/context.py`

## Source-level findings

`docling/document_converter.py` exposes `DocumentConverter`, format-specific pipelines, explicit allowed formats, maximum page count and maximum file-size controls, and a structured `DoclingDocument` result that can export to Markdown. This is materially useful when layout/table/Office/PDF structure requires more fidelity than the lightweight path.

Project Pipeline pre-checks local file size and passes bounded `max_num_pages` and `max_file_size` values into Docling. It does not make Docling the default for every file and does not allow Docling to determine instruction authority or context eligibility.

The reviewed `pyproject.toml` identifies the modular `docling-slim` package, MIT license, Python >=3.10,<4, Windows support and a smaller base dependency set. Project Pipeline therefore declares `docling-slim` as the optional structured-document dependency rather than forcing the full document stack into the baseline runtime.

## Evidence sources

- https://github.com/docling-project/docling/tree/61d76f1ff3f8428065465889f7b4577da7df704c
- https://github.com/docling-project/docling/blob/61d76f1ff3f8428065465889f7b4577da7df704c/docling/document_converter.py
- https://github.com/docling-project/docling/blob/61d76f1ff3f8428065465889f7b4577da7df704c/pyproject.toml
