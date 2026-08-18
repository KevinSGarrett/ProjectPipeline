from __future__ import annotations

import argparse
from pathlib import Path

from project_pipeline.validation.pp380_dispositions import (
    DEFAULT_OUTPUT_JSON,
    DEFAULT_OUTPUT_MD,
    DEFAULT_SOURCE_LEDGER,
    DEFAULT_SOURCE_MAP,
    PR44_DEFAULT,
    PR46_DEFAULT,
    generate_pp380_corrected_dispositions,
    write_pp380_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive PP-380 corrected dispositions from versioned source ledger, "
            "versioned source map, and explicit fetched Git refs."
        )
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-ledger", type=Path, default=None)
    parser.add_argument("--source-map", type=Path, default=None)
    parser.add_argument("--pr44-ref", default=PR44_DEFAULT)
    parser.add_argument("--pr46-ref", default=PR46_DEFAULT)
    parser.add_argument("--pp380-ref", default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    source_ledger = (
        args.source_ledger.resolve()
        if args.source_ledger is not None
        else repo_root / DEFAULT_SOURCE_LEDGER
    )
    source_map = (
        args.source_map.resolve() if args.source_map is not None else repo_root / DEFAULT_SOURCE_MAP
    )
    output_json = (
        args.output_json.resolve()
        if args.output_json is not None
        else repo_root / DEFAULT_OUTPUT_JSON
    )
    output_md = (
        args.output_md.resolve() if args.output_md is not None else repo_root / DEFAULT_OUTPUT_MD
    )
    document = generate_pp380_corrected_dispositions(
        repo_root=repo_root,
        source_ledger_path=source_ledger,
        source_map_path=source_map,
        pr44_ref=args.pr44_ref,
        pr46_ref=args.pr46_ref,
        pp380_ref=args.pp380_ref,
    )
    write_pp380_outputs(document, output_json, output_md)


if __name__ == "__main__":
    main()
