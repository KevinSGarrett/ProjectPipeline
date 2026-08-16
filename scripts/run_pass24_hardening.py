from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.release_hardening import build_hardening_report, build_release_candidate
from project_pipeline.security.supply_chain import build_repository_sbom
from project_pipeline.verification.performance import cli_help_performance, repository_validation_performance


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--measure-performance", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()

    # Performance samples must run against the already-reconciled repository state.
    # Generated release snapshots are written only after timing, otherwise they
    # would intentionally invalidate the manifest during the validator sample.
    perf = None
    if args.measure_performance:
        perf = {
            "repository_validator": repository_validation_performance(root, samples=3).model_dump(mode="json"),
            "cli_help": cli_help_performance(root, samples=5, p95_budget_ms=2500).model_dump(mode="json"),
            "phase": "final_local_hardening_performance",
            "qualification_boundary": "LOCAL_ONLY_NO_EXTERNAL_RUNTIME_CLAIM",
        }
        if not all(item.get("passed", True) for key, item in perf.items() if isinstance(item, dict)):
            return 2

    report = build_hardening_report(root)
    candidate = build_release_candidate(root)
    sbom = build_repository_sbom(root)
    write_json(root / "release/hardening_report_r24.json", report.model_dump(mode="json"))
    write_json(root / "release/release_candidate_r24.json", candidate.model_dump(mode="json"))
    write_json(root / "release/sbom_r24.json", sbom.model_dump(mode="json"))
    if perf is not None:
        write_json(root / "evidence/verification/pass24_performance.json", perf)

    print(json.dumps({"candidate": candidate.readiness, "production_ready": report.production_ready, "blocker_count": len(candidate.blockers)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
