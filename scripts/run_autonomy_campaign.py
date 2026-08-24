from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.autonomy_runtime.campaign import CampaignController
from project_pipeline.resilience.host_safety import evaluate_local_host_safety

_HOST_SAFETY_REQUIRED_ACTIONS = frozenset(
    {"start", "admit-4h", "admit-24h", "admit-72h", "run", "advance", "execute", "finalize"}
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate the autonomous qualification campaign")
    parser.add_argument(
        "action",
        choices=(
            "start",
            "admit-4h",
            "admit-24h",
            "admit-72h",
            "run",
            "status",
            "health",
            "heartbeat",
            "advance",
            "recover",
            "stop",
            "execute",
            "finalize",
            "claim-runner",
            "project-status",
        ),
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--pp384-evidence", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--reason", default="autonomy-stop")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--retry-budget", type=int, default=3)
    parser.add_argument("--service-identity")
    parser.add_argument("--command-json", help="JSON argument list for execute")
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--status-path", type=Path)
    args = parser.parse_args()
    root = (args.repository_root or Path.cwd()).resolve()
    host_safety = (
        evaluate_local_host_safety(root) if args.action in _HOST_SAFETY_REQUIRED_ACTIONS else None
    )
    if host_safety is not None and host_safety["state"] == "BLOCKED":
        print(
            json.dumps(
                {
                    "campaign": {"state": "BLOCKED", "reason": "host-safety-blocked"},
                    "host_safety": host_safety,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    controller = CampaignController(
        args.database,
        repository_root=root,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    try:
        result = _dispatch(controller, args)
        if host_safety is not None:
            result["host_safety"] = host_safety
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        controller.close()


def _dispatch(controller: CampaignController, args: argparse.Namespace) -> dict:
    if args.action == "start":
        if args.state_path is None or args.evidence_path is None or args.pp384_evidence is None:
            raise SystemExit("start requires --state-path, --evidence-path, and --pp384-evidence")
        return controller.start(
            state_path=args.state_path,
            evidence_path=args.evidence_path,
            pp384_evidence=args.pp384_evidence,
            retry_budget=args.retry_budget,
            service_identity=args.service_identity,
        )
    campaign_id = str(args.campaign_id or "")
    if not campaign_id:
        raise SystemExit(f"{args.action} requires --campaign-id")
    if args.action == "admit-4h":
        return controller.admit_4h(campaign_id)
    if args.action == "admit-24h":
        return controller.admit_24h(campaign_id)
    if args.action == "admit-72h":
        return controller.admit_72h(campaign_id)
    if args.action == "run":
        return controller.run_loop(campaign_id, cycles=args.cycles, stop_path=args.stop_file)
    if args.action == "heartbeat":
        return controller.heartbeat(campaign_id)
    if args.action == "advance":
        return controller.advance(campaign_id)
    if args.action == "recover":
        return controller.recover(campaign_id)
    if args.action == "stop":
        return controller.stop(campaign_id, reason=args.reason)
    if args.action == "execute":
        command = json.loads(args.command_json or "[]")
        if not isinstance(command, list):
            raise SystemExit("--command-json must be a JSON argument list")
        return controller.execute(campaign_id, [str(item) for item in command])
    if args.action == "finalize":
        return controller.finalize(campaign_id)
    if args.action == "claim-runner":
        return controller.claim_runner_ownership(campaign_id)
    if args.action == "project-status":
        if args.status_path is None:
            raise SystemExit("project-status requires --status-path")
        return controller.project_status(campaign_id, status_path=args.status_path)
    return controller.health(campaign_id)


if __name__ == "__main__":
    raise SystemExit(main())
