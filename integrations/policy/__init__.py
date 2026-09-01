"""Policy conformance integrations (OPA/Conftest)."""

from integrations.policy.opa import OpaConformancePolicyPort, build_default_policy_port

__all__ = ["OpaConformancePolicyPort", "build_default_policy_port"]
