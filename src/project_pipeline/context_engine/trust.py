from __future__ import annotations

from enum import StrEnum

from project_pipeline.domain.context import ContextSourceKind, ContextTrust


class InstructionOrigin(StrEnum):
    GOVERNING_CONTRACT = "GOVERNING_CONTRACT"
    SOURCE_CONTROLLED_POLICY = "SOURCE_CONTROLLED_POLICY"
    SOURCE_CONTROLLED_INSTRUCTION = "SOURCE_CONTROLLED_INSTRUCTION"
    VERIFIED_EXTERNAL_EVIDENCE = "VERIFIED_EXTERNAL_EVIDENCE"
    REPOSITORY_CONTENT = "REPOSITORY_CONTENT"
    BROWSER_OR_EXTERNAL_DOCUMENT = "BROWSER_OR_EXTERNAL_DOCUMENT"


def classify_instruction_trust(origin: InstructionOrigin) -> ContextTrust:
    """Classify instruction/evidence authority from an explicit provenance origin."""
    mapping = {
        InstructionOrigin.GOVERNING_CONTRACT: ContextTrust.GOVERNING,
        InstructionOrigin.SOURCE_CONTROLLED_POLICY: ContextTrust.AUTHORITATIVE,
        InstructionOrigin.SOURCE_CONTROLLED_INSTRUCTION: ContextTrust.SOURCE_CONTROLLED,
        InstructionOrigin.VERIFIED_EXTERNAL_EVIDENCE: ContextTrust.VERIFIED_EXTERNAL,
        InstructionOrigin.REPOSITORY_CONTENT: ContextTrust.UNTRUSTED_REPOSITORY,
        InstructionOrigin.BROWSER_OR_EXTERNAL_DOCUMENT: ContextTrust.UNTRUSTED_EXTERNAL,
    }
    return mapping[origin]


def instruction_kind_allowed_as_authority(kind: ContextSourceKind, trust: ContextTrust) -> bool:
    """Return true only for instruction/policy material with an authority-bearing trust class."""
    if kind not in {ContextSourceKind.INSTRUCTION, ContextSourceKind.POLICY}:
        return False
    return trust in {
        ContextTrust.GOVERNING,
        ContextTrust.AUTHORITATIVE,
        ContextTrust.SOURCE_CONTROLLED,
    }
