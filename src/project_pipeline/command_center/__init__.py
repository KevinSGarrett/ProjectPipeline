from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AGUIAdapter",
    "AppriseNotificationAdapter",
    "AttentionNotificationBroker",
    "CommandCenterApplicationProjection",
    "CommandCenterAuth",
    "CommandCenterControlGateway",
    "CommandCenterProjectionService",
    "CommandCenterScope",
    "CommandCenterSnapshot",
    "CommandCenterStore",
    "DeterministicGroundedDirectorResponder",
    "DirectorActionProposal",
    "DirectorChatMessage",
    "DirectorChatRequest",
    "DirectorChatResponse",
    "DirectorChatService",
    "DirectorContextBuilder",
    "HealthDimension",
    "HealthState",
    "InboxItem",
    "InboxState",
    "IncidentCase",
    "IncidentManager",
    "IncidentState",
    "IncidentVerificationRequest",
    "NotificationDecision",
    "NotificationDeliveryAttempt",
    "NotificationDeliveryService",
    "NotificationDeliveryState",
    "NotificationDispatchResult",
    "NotificationLevel",
    "NotificationPolicy",
    "NtfyHttpNotificationAdapter",
    "RealtimeEventBroker",
    "RepositoryApplicationProjectionBuilder",
    "TimelinePage",
    "create_command_center_app",
    "validate_command_center_application",
    "validate_command_center_foundation",
]

_EXPORT_MODULES = {
    "AGUIAdapter": "project_pipeline.command_center.agui",
    "AppriseNotificationAdapter": "project_pipeline.command_center.notifications",
    "AttentionNotificationBroker": "project_pipeline.command_center.inbox",
    "CommandCenterApplicationProjection": "project_pipeline.command_center.application",
    "CommandCenterAuth": "project_pipeline.command_center.api",
    "CommandCenterControlGateway": "project_pipeline.command_center.director",
    "CommandCenterProjectionService": "project_pipeline.command_center.projections",
    "CommandCenterScope": "project_pipeline.command_center.models",
    "CommandCenterSnapshot": "project_pipeline.command_center.models",
    "CommandCenterStore": "project_pipeline.command_center.persistence",
    "DeterministicGroundedDirectorResponder": "project_pipeline.command_center.director",
    "DirectorActionProposal": "project_pipeline.command_center.models",
    "DirectorChatMessage": "project_pipeline.command_center.models",
    "DirectorChatRequest": "project_pipeline.command_center.models",
    "DirectorChatResponse": "project_pipeline.command_center.models",
    "DirectorChatService": "project_pipeline.command_center.director",
    "DirectorContextBuilder": "project_pipeline.command_center.director",
    "HealthDimension": "project_pipeline.command_center.models",
    "HealthState": "project_pipeline.command_center.models",
    "InboxItem": "project_pipeline.command_center.models",
    "InboxState": "project_pipeline.command_center.models",
    "IncidentCase": "project_pipeline.command_center.models",
    "IncidentManager": "project_pipeline.command_center.incidents",
    "IncidentState": "project_pipeline.command_center.models",
    "IncidentVerificationRequest": "project_pipeline.command_center.models",
    "NotificationDecision": "project_pipeline.command_center.models",
    "NotificationDeliveryAttempt": "project_pipeline.command_center.models",
    "NotificationDeliveryService": "project_pipeline.command_center.notifications",
    "NotificationDeliveryState": "project_pipeline.command_center.models",
    "NotificationDispatchResult": "project_pipeline.command_center.models",
    "NotificationLevel": "project_pipeline.command_center.models",
    "NotificationPolicy": "project_pipeline.command_center.models",
    "NtfyHttpNotificationAdapter": "project_pipeline.command_center.notifications",
    "RealtimeEventBroker": "project_pipeline.command_center.realtime",
    "RepositoryApplicationProjectionBuilder": "project_pipeline.command_center.application",
    "TimelinePage": "project_pipeline.command_center.models",
    "create_command_center_app": "project_pipeline.command_center.api",
    "validate_command_center_application": (
        "project_pipeline.command_center.application_validation"
    ),
    "validate_command_center_foundation": "project_pipeline.command_center.validation",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
