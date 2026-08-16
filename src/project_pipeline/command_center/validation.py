from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.command_center.simulation import run_command_center_simulations

_REQUIRED = (
    "src/project_pipeline/command_center/api.py",
    "src/project_pipeline/command_center/realtime.py",
    "src/project_pipeline/command_center/inbox.py",
    "src/project_pipeline/command_center/director.py",
    "src/project_pipeline/command_center/agui.py",
    "src/project_pipeline/command_center/incidents.py",
    "src/project_pipeline/command_center/notifications.py",
    "config/command_center_policy.json",
    "database/migrations/sqlite/PPDB-0016_command_center_realtime.up.sql",
    "database/migrations/postgresql/PPDB-0016_command_center_realtime.up.sql",
    "database/migrations/sqlite/PPDB-0017_director_incident_notifications.up.sql",
    "database/migrations/postgresql/PPDB-0017_director_incident_notifications.up.sql",
    "docs/command_center/backend_realtime_api.md",
    "docs/command_center/director_incident_notifications.md",
    "runbooks/operator_notification_failure_recovery.md",
    "provenance/pass_21_upstream_gate.json",
)


def validate_command_center_foundation(root: Path) -> list[str]:
    errors = []
    for rel in _REQUIRED:
        if not (root / rel).exists():
            errors.append(f"missing Command Center artifact: {rel}")
    policy_path = root / "config/command_center_policy.json"
    if policy_path.exists():
        p = json.loads(policy_path.read_text())
        if p.get("canonical_authority") != "PROJECT_PIPELINE":
            errors.append("Command Center policy must preserve PROJECT_PIPELINE authority")
        if p.get("ui_state_authoritative") is not False:
            errors.append("Command Center UI state must be non-authoritative")
        if p.get("anonymous_control_allowed") is not False:
            errors.append("anonymous Command Center control must be denied")
        if p.get("realtime", {}).get("replay_cursor") != "EventEnvelope.sequence":
            errors.append("realtime replay cursor must use EventEnvelope.sequence")
        director = p.get("director", {})
        if director.get("raw_text_may_mutate_state") is not False:
            errors.append("Director raw text must not mutate canonical state")
        if director.get("typed_action_intent_required_for_mutation") is not True:
            errors.append("Director mutations must require typed ActionIntent")
        notifications = p.get("notifications", {})
        if notifications.get("initial_remote_adapter") != "apprise":
            errors.append("Pass 21 initial remote adapter must be Apprise")
        if notifications.get("remote_channels_enabled_by_default") is not False:
            errors.append("remote notifications must remain disabled by default")
        if notifications.get("ntfy_role") != "optional_self_hosted_target_or_adapter":
            errors.append("ntfy must remain an optional delivery target/adapter")
    gate = root / "provenance/upstream_adoption_gate.json"
    if gate.exists():
        data = json.loads(gate.read_text())
        subsystems = data.get("subsystems", {}) if isinstance(data, dict) else {}
        if isinstance(subsystems, dict):
            record = subsystems.get("command_center", {})
            if record.get("review_state") != "INTEGRATED":
                errors.append("Command Center upstream-first gate is not INTEGRATED")
            interaction = subsystems.get("director_incident_notifications", {})
            if interaction.get("review_state") != "INTEGRATED":
                errors.append(
                    "Pass 21 Director/incident/notification upstream gate is not INTEGRATED"
                )
        else:
            match = [
                x
                for x in subsystems
                if str(x.get("subsystem_id", x.get("subsystem", ""))).lower() == "command_center"
            ]
            if not match or match[0].get("review_state") != "INTEGRATED":
                errors.append("Command Center upstream-first gate is not INTEGRATED")
    results = run_command_center_simulations()
    for name, ok in results.items():
        if not ok:
            errors.append(f"Command Center simulation failed: {name}")
    return errors
