from __future__ import annotations

from project_pipeline.contracts import ActionIntent, ApprovalState
from project_pipeline.domain.security import (
    ApprovalRecord,
    AuthorityCapability,
    DataClassification,
    EgressDecision,
    EgressRequest,
    PolicyDecision,
    PolicyDisposition,
    security_fingerprint,
    security_identifier,
)
from project_pipeline.security.identity import IdentityAuthority

_HIGH_IMPACT = {
    AuthorityCapability.MERGE,
    AuthorityCapability.DEPLOY,
    AuthorityCapability.SPEND,
    AuthorityCapability.EXTERNAL_MODEL,
    AuthorityCapability.ACCESS_SECRET,
    AuthorityCapability.MODIFY_INSTRUCTIONS,
    AuthorityCapability.MODIFY_POLICY,
    AuthorityCapability.COMPLETE_PROJECT,
    AuthorityCapability.EMERGENCY,
}


def classify_action_capability(operation: str) -> AuthorityCapability:
    normalized = operation.lower().replace("-", "_").replace(":", "_")
    ordered = (
        (("modify_policy", "policy_change"), AuthorityCapability.MODIFY_POLICY),
        (("instruction", "governing_instruction"), AuthorityCapability.MODIFY_INSTRUCTIONS),
        (("complete", "completion"), AuthorityCapability.COMPLETE_PROJECT),
        (("deploy", "release"), AuthorityCapability.DEPLOY),
        (("merge",), AuthorityCapability.MERGE),
        (("spend", "purchase", "budget"), AuthorityCapability.SPEND),
        (("external_model", "provider", "llm"), AuthorityCapability.EXTERNAL_MODEL),
        (("secret", "credential"), AuthorityCapability.ACCESS_SECRET),
        (("approve",), AuthorityCapability.APPROVE),
        (("read", "get", "list", "inspect"), AuthorityCapability.READ),
        (("propose", "plan"), AuthorityCapability.PROPOSE),
    )
    for words, capability in ordered:
        if any(word in normalized for word in words):
            return capability
    return AuthorityCapability.MUTATE


class SecurityPolicyEngine:
    """Canonical deterministic security policy semantics; OPA is an optional conformance backend."""

    policy_version = "SECURITY-POLICY-1.0.0"

    def __init__(
        self,
        authority: IdentityAuthority,
        *,
        external_provider_allowlist: tuple[str, ...] = (),
        external_destination_allowlist: tuple[str, ...] = (),
    ) -> None:
        self.authority = authority
        self.external_provider_allowlist = external_provider_allowlist
        self.external_destination_allowlist = external_destination_allowlist

    def evaluate_action(
        self,
        intent: ActionIntent,
        *,
        project_id: str,
        environment: str,
        approval: ApprovalRecord | None = None,
    ) -> PolicyDecision:
        capability = classify_action_capability(intent.operation)
        input_doc = {
            "action": intent.model_dump(mode="json"),
            "project_id": project_id,
            "environment": environment,
            "capability": capability.value,
            "approval_id": approval.approval_id if approval else None,
        }
        authorized = self.authority.authorize(
            intent.actor_id,
            capability,
            project_id=project_id,
            target=intent.target,
            environment=environment,
            operation=capability.value,
            risk=intent.risk.value,
        )
        reasons: list[str] = []
        approval_required = capability in _HIGH_IMPACT
        if not authorized:
            disposition = PolicyDisposition.DENY
            reasons.append(
                "actor lacks least-privilege authority for requested capability, scope, environment, or risk"
            )
        elif approval_required:
            approved = (
                approval is not None
                and approval.action_id == intent.action_id
                and approval.proposer_identity_id == intent.actor_id
                and approval.capability is capability
                and self.authority.validate_approval(
                    approval,
                    project_id=project_id,
                    target=intent.target,
                    environment=environment,
                    risk=intent.risk.value,
                )
            )
            if not approved:
                disposition = PolicyDisposition.REQUIRE_APPROVAL
                reasons.append("high-impact action requires independent authorized approval")
            elif intent.approval_state is not ApprovalState.APPROVED:
                disposition = PolicyDisposition.REQUIRE_APPROVAL
                reasons.append("action intent does not record approved state")
            else:
                disposition = PolicyDisposition.ALLOW
                reasons.append("least-privilege authority and independent approval are satisfied")
        else:
            disposition = PolicyDisposition.ALLOW
            reasons.append("least-privilege authority is satisfied")
        return PolicyDecision(
            decision_id=security_identifier(
                "POLICY", intent.action_id, self.policy_version, disposition.value
            ),
            policy_version=self.policy_version,
            action_id=intent.action_id,
            actor_identity_id=intent.actor_id,
            capability=capability,
            disposition=disposition,
            reasons=tuple(reasons),
            constraints={
                "project_id": project_id,
                "environment": environment,
                "target": intent.target,
            },
            approval_required=approval_required,
            input_fingerprint=security_fingerprint(input_doc),
        )

    def evaluate_egress(self, request: EgressRequest) -> EgressDecision:
        reasons: list[str] = []
        allowed_keys = tuple(request.context_keys)
        redacted: tuple[str, ...] = ()
        if request.contains_secret:
            disposition = PolicyDisposition.DENY
            reasons.append("detected secret material may not be transmitted externally")
        elif request.classification in {DataClassification.SECRET, DataClassification.LOCAL_ONLY}:
            disposition = PolicyDisposition.DENY
            reasons.append(
                f"{request.classification.value} data is not eligible for external egress"
            )
        elif (
            self.external_provider_allowlist
            and request.provider_id not in self.external_provider_allowlist
        ):
            disposition = PolicyDisposition.DENY
            reasons.append("provider is not eligible under project egress policy")
        elif (
            self.external_destination_allowlist
            and request.destination not in self.external_destination_allowlist
        ):
            disposition = PolicyDisposition.DENY
            reasons.append("destination is not eligible under project egress policy")
        elif request.classification is DataClassification.CONFIDENTIAL:
            disposition = PolicyDisposition.REQUIRE_APPROVAL
            reasons.append("confidential egress requires explicit authorization")
        elif request.contains_untrusted_instructions:
            disposition = PolicyDisposition.CONSTRAIN
            reasons.append(
                "untrusted instructions may be transmitted only as data and cannot alter governing authority"
            )
        else:
            disposition = PolicyDisposition.ALLOW
            reasons.append("classification, provider and destination satisfy egress policy")
        return EgressDecision(
            decision_id=security_identifier(
                "POLICY", request.request_id, "egress", disposition.value
            ),
            request_id=request.request_id,
            disposition=disposition,
            allowed_context_keys=allowed_keys,
            redacted_context_keys=redacted,
            reasons=tuple(reasons),
        )

    @staticmethod
    def instruction_authoritative(
        *, origin: str, signed_or_trusted: bool, requested_authority_change: bool
    ) -> tuple[bool, str]:
        trusted_origins = {"governing_prompt", "trusted_policy", "operator_approved_instruction"}
        if origin not in trusted_origins or not signed_or_trusted:
            return False, "untrusted source is data, not governing instruction"
        if requested_authority_change and origin != "operator_approved_instruction":
            return (
                False,
                "authority modification requires explicitly reviewed operator-approved instruction",
            )
        return True, "trusted instruction origin and review state satisfy policy"
