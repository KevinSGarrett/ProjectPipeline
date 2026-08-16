from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path

from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate
from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.application import RepositoryApplicationProjectionBuilder
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker


def build_app(root: Path):
    root=root.resolve()
    projection=CommandCenterProjectionService()
    def snapshot():
        gate=evaluate_completion_gate(build_repository_gate_facts(root,"PROJECT-PIPELINE"))
        return projection.build_snapshot(snapshot_id="cc:service",project_id="PROJECT-PIPELINE",operating_mode="NORMAL",health=(HealthDimension(name="repository",state=HealthState.HEALTHY,reason="repository-local service projection"),),completion_gate_state=gate.state.value,evidence_count=sum(1 for line in (root/"evidence/EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()))
    configured=os.environ.get("PROJECT_PIPELINE_COMMAND_CENTER_TOKEN")
    def validate(token: str) -> str | None:
        if not configured or not hmac.compare_digest(token,configured): return None
        return "local-operator"
    return create_command_center_app(snapshot_provider=snapshot,event_broker=RealtimeEventBroker(),inbox=AttentionNotificationBroker(),application_provider=lambda: RepositoryApplicationProjectionBuilder(root).build(snapshot()),auth=CommandCenterAuth(validate))


def main() -> int:
    parser=argparse.ArgumentParser(description="Run the bounded Project Pipeline Command Center service")
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    app=build_app(args.root)
    if args.check:
        print(json.dumps({"status":"SOURCE_RUNTIME_CHECK_PASS","route_count":len(app.routes),"auth_token_configured":bool(os.environ.get("PROJECT_PIPELINE_COMMAND_CENTER_TOKEN")),"canonical_authority":"PROJECT_PIPELINE"},sort_keys=True))
        return 0
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,log_level="info")
    return 0

if __name__ == "__main__": raise SystemExit(main())
