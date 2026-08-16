from project_pipeline.context_engine.trust import (
    InstructionOrigin,
    classify_instruction_trust,
    instruction_kind_allowed_as_authority,
)
from project_pipeline.domain.context import ContextSourceKind, ContextTrust


def test_governing_and_source_controlled_instruction_origins_are_authority_bearing():
    assert (
        classify_instruction_trust(InstructionOrigin.GOVERNING_CONTRACT) is ContextTrust.GOVERNING
    )
    assert (
        classify_instruction_trust(InstructionOrigin.SOURCE_CONTROLLED_INSTRUCTION)
        is ContextTrust.SOURCE_CONTROLLED
    )
    assert instruction_kind_allowed_as_authority(
        ContextSourceKind.INSTRUCTION, ContextTrust.GOVERNING
    )
    assert instruction_kind_allowed_as_authority(
        ContextSourceKind.POLICY, ContextTrust.AUTHORITATIVE
    )


def test_repository_and_external_document_origins_never_become_instruction_authority():
    assert (
        classify_instruction_trust(InstructionOrigin.REPOSITORY_CONTENT)
        is ContextTrust.UNTRUSTED_REPOSITORY
    )
    assert (
        classify_instruction_trust(InstructionOrigin.BROWSER_OR_EXTERNAL_DOCUMENT)
        is ContextTrust.UNTRUSTED_EXTERNAL
    )
    assert not instruction_kind_allowed_as_authority(
        ContextSourceKind.INSTRUCTION, ContextTrust.UNTRUSTED_REPOSITORY
    )
    assert not instruction_kind_allowed_as_authority(
        ContextSourceKind.POLICY, ContextTrust.UNTRUSTED_EXTERNAL
    )


def test_verified_external_evidence_is_not_instruction_authority():
    trust = classify_instruction_trust(InstructionOrigin.VERIFIED_EXTERNAL_EVIDENCE)
    assert trust is ContextTrust.VERIFIED_EXTERNAL
    assert not instruction_kind_allowed_as_authority(ContextSourceKind.DOCUMENT, trust)
