from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
from pathlib import Path

from project_pipeline.domain.verification import (
    ToolActivationState,
    VerificationToolActivation,
    verification_identifier,
)

_CANDIDATES = (
    ("UPSTREAM-015", "boxed/mutmut", "BSD-3-Clause", "mutmut", None),
    ("UPSTREAM-027", "dequelabs/axe-core", "MPL-2.0", None, None),
    ("UPSTREAM-032", "EleutherAI/lm-evaluation-harness", "MIT", None, None),
    ("UPSTREAM-044", "GoogleChrome/lighthouse-ci", "Apache-2.0", "lhci", None),
    ("UPSTREAM-051", "HypothesisWorks/hypothesis", "MPL-2.0", None, "hypothesis"),
    ("UPSTREAM-063", "microsoft/playwright", "Apache-2.0", "playwright", "playwright"),
    ("UPSTREAM-064", "microsoft/playwright-mcp", "Apache-2.0", "playwright-mcp", None),
    ("UPSTREAM-085", "promptfoo/promptfoo", "MIT", "promptfoo", None),
    ("UPSTREAM-092", "schemathesis/schemathesis", "MIT", "schemathesis", "schemathesis"),
    ("UPSTREAM-093", "Shopify/toxiproxy", "MIT", "toxiproxy-server", None),
    ("UPSTREAM-101", "stryker-mutator/stryker-js", "Apache-2.0", None, None),
    ("UPSTREAM-108", "UKGovernmentBEIS/inspect_ai", "MIT", "inspect", "inspect_ai"),
    ("UPSTREAM-111", "vercel-labs/agent-browser", "Apache-2.0", "agent-browser", None),
)

_REVISIONS = {
    "UPSTREAM-051": "16f24b76015dbaabca40608eb9e73b46ac64e249",
    "UPSTREAM-063": "d5a185a894ab3ab17ff77a44e116a1339c6bdaed",
    "UPSTREAM-064": "7e0457a7cbf88823bf0146d12c46ae12c6818247",
    "UPSTREAM-085": "fded938b65a81e12070a66e90ca4ad2d42a8062e",
    "UPSTREAM-092": "c60bde9733dad2fc4ef8f6451f58a10e8c7b6663",
    "UPSTREAM-093": "94d6d4b3c385e48534622b138da61e95014196d5",
    "UPSTREAM-108": "c07dff4f8c029d92e785bf4109f5ed43f582c880",
    "UPSTREAM-111": "548b159b30eef119ccf6846c8bc807d0eaa3f6f8",
}

_EXISTING_ADAPTERS = {
    "UPSTREAM-085": ("src/project_pipeline/upstream_integrations/evaluation.py",),
    "UPSTREAM-108": ("src/project_pipeline/upstream_integrations/evaluation.py",),
}

_NEW_ADAPTERS = {
    "UPSTREAM-015": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-027": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-044": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-051": ("src/project_pipeline/verification/property_checks.py",),
    "UPSTREAM-063": ("src/project_pipeline/verification/browser.py",),
    "UPSTREAM-064": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-092": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-093": ("src/project_pipeline/verification/external_tools.py",),
    "UPSTREAM-111": ("src/project_pipeline/verification/external_tools.py",),
}

_PATTERN_ONLY = {"UPSTREAM-032", "UPSTREAM-101"}


def _module_version(module_name: str) -> str | None:
    if importlib.util.find_spec(module_name) is None:
        return None
    candidates = {
        "playwright": "playwright",
        "hypothesis": "hypothesis",
        "schemathesis": "schemathesis",
        "inspect_ai": "inspect-ai",
    }
    try:
        return importlib.metadata.version(candidates.get(module_name, module_name))
    except importlib.metadata.PackageNotFoundError:
        return "installed-version-unknown"


def activation_snapshot(
    root: Path,
    *,
    executed_upstream_ids: tuple[str, ...] = (),
    evidence_by_upstream: dict[str, tuple[str, ...]] | None = None,
) -> tuple[VerificationToolActivation, ...]:
    evidence_by_upstream = evidence_by_upstream or {}
    values: list[VerificationToolActivation] = []
    executed = set(executed_upstream_ids)
    for upstream_id, repository, license_name, binary, module_name in _CANDIDATES:
        binary_path = shutil.which(binary) if binary else None
        module_version = _module_version(module_name) if module_name else None
        paths = _EXISTING_ADAPTERS.get(upstream_id, ()) + _NEW_ADAPTERS.get(upstream_id, ())
        if upstream_id in _PATTERN_ONLY:
            state = ToolActivationState.PATTERN_ONLY
            reason = "Test/verification pattern source; no runtime activation is required."
        elif upstream_id in executed:
            state = ToolActivationState.EXECUTED
            reason = "Verification capability executed in the current Pass 16 environment with captured evidence."
        elif paths:
            state = ToolActivationState.ADAPTER_IMPLEMENTED
            if binary_path or module_version:
                reason = "Concrete adapter/harness path is implemented; executable/module is present but was not required for this evidence run."
            else:
                reason = "Concrete adapter/harness path is implemented; external executable/module is not installed in the current environment."
        else:
            state = ToolActivationState.QUALIFIED_NOT_INSTALLED
            reason = "Capability remains qualified but no Project Pipeline adapter or installed runtime is claimed."
        values.append(
            VerificationToolActivation(
                activation_id=verification_identifier("VTOOL", upstream_id, state.value, "PASS16"),
                upstream_id=upstream_id,
                repository=repository,
                state=state,
                installed_version=module_version,
                executable_path=binary_path,
                integration_paths=tuple(paths),
                evidence_paths=evidence_by_upstream.get(upstream_id, ()),
                activation_phase="PASS16_VERIFICATION_HARNESS",
                reason=reason,
                source_revision=_REVISIONS.get(upstream_id),
                license=license_name,
            )
        )
    return tuple(values)
