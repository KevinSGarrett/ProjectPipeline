from __future__ import annotations

from project_pipeline.contracts import AdapterErrorPayload


class GitHubStewardError(RuntimeError):
    """Fail-closed repository stewardship error."""


class GitHubAdapterError(GitHubStewardError):
    def __init__(self, payload: AdapterErrorPayload) -> None:
        self.payload = payload
        super().__init__(payload.message)
