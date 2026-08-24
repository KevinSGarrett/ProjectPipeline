"""Execute one bounded, read-only campaign duration probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.autonomy_runtime.duration_probes import run_duration_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an evidence-bearing duration probe")
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--campaign-database", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--candidate-evidence", type=Path)
    parser.add_argument("--state-root", type=Path)
    args = parser.parse_args()
    result = run_duration_probe(
        args.probe_id,
        repository_root=args.repository_root,
        expected_sha=args.expected_sha,
        expected_tree=args.expected_tree,
        campaign_database=args.campaign_database,
        campaign_id=args.campaign_id,
        candidate_evidence=args.candidate_evidence,
        state_root=args.state_root,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
