from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.live_qualification import (  # noqa: E402
    run_live_qualification,
    write_live_qualification_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PP-384 stage-C live qualification checks")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--disposable-root", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--attestation-source-root", type=Path)
    parser.add_argument("--durable-dir", type=Path)
    parser.add_argument("--coordinator-jira-receipt", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    if args.write_evidence:
        output = write_live_qualification_evidence(
            repository_root=args.root.resolve(),
            evidence_dir=args.evidence_dir,
            disposable_root=args.disposable_root,
            attestation_source_root=args.attestation_source_root,
            durable_dir=args.durable_dir,
            coordinator_jira_receipt=args.coordinator_jira_receipt,
        )
        print(json.dumps({"written": str(output)}, indent=2, sort_keys=True))
        return 0
    report = run_live_qualification(
        repository_root=args.root.resolve(),
        disposable_root=args.disposable_root,
        attestation_source_root=args.attestation_source_root,
        durable_dir=args.durable_dir,
        coordinator_jira_receipt=args.coordinator_jira_receipt,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
