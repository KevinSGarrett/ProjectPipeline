"""Local-first product profile constraints for REQ-PDEF-0007/0008/0010."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json

CONSUMER_CHAT_MARKERS = (
    "consumer chat browser",
    "chatgpt.com",
    "claude.ai/new",
    "automate a consumer chat",
)


def evaluate_product_profile(root: Path) -> dict[str, Any]:
    """Fail closed when local-first, unpaid-default, or chat-exclusion is violated."""

    root = root.resolve()
    project = read_json(root / "config" / "project.json")
    operating_model = str(project.get("operating_model") or "").casefold()
    local_first = "local-first" in operating_model or bool(project.get("local_first"))
    paid_required = bool(project.get("paid_service_required_by_default"))
    blob = str(project).casefold()
    consumer_chat = any(marker in blob for marker in CONSUMER_CHAT_MARKERS)
    reasons: list[str] = []
    if not local_first:
        reasons.append("operating_model_not_local_first")
    if paid_required:
        reasons.append("paid_service_required_by_default")
    if consumer_chat:
        reasons.append("consumer_chat_automation_dependency")
    return {
        "schema_version": "1.0.0",
        "ok": not reasons,
        "local_first": local_first,
        "paid_service_required_by_default": paid_required,
        "consumer_chat_automation_excluded": not consumer_chat,
        "cloud_optional": "optional" in operating_model or "local-first" in operating_model,
        "reasons": reasons,
        "user_action_required": False,
    }
