from project_pipeline.lifecycle.adoption import assess_adoption_maturity
from project_pipeline.lifecycle.contracts import ContractEvolutionManager
from project_pipeline.lifecycle.environments import EnvironmentManager, TestDataLifecycleManager
from project_pipeline.lifecycle.portfolio import PortfolioGovernor
from project_pipeline.lifecycle.qualification import (
    PlatformUpgradeGovernor,
    VersionQualificationManager,
)
from project_pipeline.lifecycle.repositories import MultiRepositoryCoordinator
from project_pipeline.lifecycle.retention import InformationLifecycleManager, ProjectClosureDirector
from project_pipeline.lifecycle.simulation import simulate_scenario, supported_scenarios
from project_pipeline.lifecycle.takeover import (
    PP327_BLOCKED_PATHS,
    AttestationState,
    AttestationValidation,
    CheckpointDecision,
    DurableAttestation,
    DurableProviderQualificationEvidence,
    LaneState,
    ProviderQualificationState,
    ProviderQualificationValidation,
    ReadinessEvidence,
    SessionIdentity,
    claim_is_admissible,
    global_stop_required,
    local_integration_allowed,
    pp327_collision,
    provider_dispatch_blocked,
    scoped_lane_state,
    should_request_human_attestation,
    validate_durable_attestation,
    validate_provider_qualification_evidence,
)
from project_pipeline.lifecycle.validation import validate_lifecycle_foundation

CANONICAL_PURSUING_GOAL = (
    "Deliver and qualify ProjectPipeline as a continuously operating, local-first autonomous "
    "engineering organization that accepts complete project inputs, compiles a verified project "
    "model, autonomously selects and executes genuinely missing work through conflict-safe "
    "parallel lanes and qualified workers, verifies results, governs GitHub and Jira, merges "
    "accepted changes, reconciles external state, recomputes project state, handles "
    "HUMAN_REQUIRED incidents without stopping unaffected work, exposes truthful live state "
    "through the Command Center, and continues until the deterministic Completion Gate reports "
    "COMPLETE for the integrated, released, and operationally verified system."
)
CANONICAL_SOURCE_REFERENCES = (
    "SRC-014:L000001-L000087",
    "SRC-015:L000031-L000150",
)

__all__ = [
    "CANONICAL_PURSUING_GOAL",
    "CANONICAL_SOURCE_REFERENCES",
    "PP327_BLOCKED_PATHS",
    "AttestationState",
    "AttestationValidation",
    "CheckpointDecision",
    "ContractEvolutionManager",
    "DurableAttestation",
    "DurableProviderQualificationEvidence",
    "EnvironmentManager",
    "InformationLifecycleManager",
    "LaneState",
    "MultiRepositoryCoordinator",
    "PlatformUpgradeGovernor",
    "PortfolioGovernor",
    "ProjectClosureDirector",
    "ProviderQualificationState",
    "ProviderQualificationValidation",
    "ReadinessEvidence",
    "SessionIdentity",
    "TestDataLifecycleManager",
    "VersionQualificationManager",
    "assess_adoption_maturity",
    "claim_is_admissible",
    "global_stop_required",
    "local_integration_allowed",
    "pp327_collision",
    "provider_dispatch_blocked",
    "scoped_lane_state",
    "should_request_human_attestation",
    "simulate_scenario",
    "supported_scenarios",
    "validate_durable_attestation",
    "validate_lifecycle_foundation",
    "validate_provider_qualification_evidence",
]
