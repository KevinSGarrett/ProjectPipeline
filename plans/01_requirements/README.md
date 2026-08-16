# Requirements

This domain contains the requirements-engineering plan, the detailed catalog-and-coverage plan, the machine-readable glossary, unresolved-decision registry, and source-evolution registry.

The canonical requirement catalog and all bidirectional mapping exports live under `plans/_traceability/`. `source_sections.jsonl` explicitly dispositions every canonical source section so contextual examples, research, duplicates, and unresolved choices are not silently lost or misrepresented as accepted requirements.

Use `PYTHONPATH=src python -m project_pipeline requirements --root . --summary` for a catalog summary and `--id`, `--domain`, `--source`, `--priority`, `--state`, or `--text` for focused retrieval.
