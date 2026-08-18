from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier
from project_pipeline.domain.requirements import ImplementationState
from project_pipeline.ids import ACCEPTANCE_ID, ISSUE_ID, PLAN_ID, PLAN_SECTION_ID
from project_pipeline.source_references import parse_source_reference

REMOTE_JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]*$")
HEX_64 = re.compile(r"^[a-f0-9]{64}$")
JIRA_SYNC_ID = re.compile(r"^(JSNAP|JPLAN|JOP|JREC|JCON|JCOM)-[A-F0-9]{20}$")


def _digest_payload(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def jira_sync_identifier(
    prefix: Literal["JSNAP", "JPLAN", "JOP", "JREC", "JCON", "JCOM"], *parts: str
) -> str:
    canonical = "\x1f".join(part.strip() for part in parts)
    if not canonical or any(not part.strip() for part in parts):
        raise ValueError("Jira synchronization identifier parts must be non-empty")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20].upper()
    return f"{prefix}-{digest}"


class JiraIssueType(StrEnum):
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"
    SUBTASK = "SUBTASK"
    BUG = "BUG"
    SPIKE = "SPIKE"


class JiraLifecycleState(StrEnum):
    DISCOVERED = "DISCOVERED"
    BACKLOG = "BACKLOG"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    VALIDATION = "VALIDATION"
    MERGE_READY = "MERGE_READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEFERRED = "DEFERRED"
    DONE = "DONE"


class JiraRelationshipType(StrEnum):
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    BLOCKS = "BLOCKS"
    BLOCKED_BY = "BLOCKED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    REQUIRED_BY = "REQUIRED_BY"
    RELATES_TO = "RELATES_TO"
    IMPLEMENTS_REQUIREMENT = "IMPLEMENTS_REQUIREMENT"
    VERIFIED_BY = "VERIFIED_BY"
    SOURCE_OF = "SOURCE_OF"
    SUPERSEDES = "SUPERSEDES"
    CONFLICTS_WITH = "CONFLICTS_WITH"


class JiraCommentKind(StrEnum):
    WORK_STARTED = "WORK_STARTED"
    DECISION = "DECISION"
    BLOCKER = "BLOCKER"
    SCOPE_CHANGE = "SCOPE_CHANGE"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    REVIEW_FINDING = "REVIEW_FINDING"
    RECOVERY_HANDOFF = "RECOVERY_HANDOFF"
    VALIDATION_EVIDENCE = "VALIDATION_EVIDENCE"
    COMPLETION_SUMMARY = "COMPLETION_SUMMARY"


class JiraAuthorityMode(StrEnum):
    SOURCE_CONTROLLED_LOCAL = "SOURCE_CONTROLLED_LOCAL"
    REMOTE_COLLABORATIVE = "REMOTE_COLLABORATIVE"


class JiraSnapshotSource(StrEnum):
    LOCAL_MIRROR = "LOCAL_MIRROR"
    REMOTE_JIRA = "REMOTE_JIRA"
    IMPORT_BUNDLE = "IMPORT_BUNDLE"


class JiraSyncMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    APPLY = "APPLY"


class JiraSyncOperationType(StrEnum):
    CREATE_REMOTE_ISSUE = "CREATE_REMOTE_ISSUE"
    UPDATE_REMOTE_FIELDS = "UPDATE_REMOTE_FIELDS"
    TRANSITION_REMOTE_ISSUE = "TRANSITION_REMOTE_ISSUE"
    ADD_REMOTE_COMMENT = "ADD_REMOTE_COMMENT"
    CREATE_REMOTE_LINK = "CREATE_REMOTE_LINK"
    RECORD_REMOTE_MAPPING = "RECORD_REMOTE_MAPPING"
    IMPORT_REMOTE_ISSUE = "IMPORT_REMOTE_ISSUE"
    ACCEPT_REMOTE_FIELDS = "ACCEPT_REMOTE_FIELDS"
    NO_OPERATION = "NO_OPERATION"


class JiraOperationState(StrEnum):
    PLANNED = "PLANNED"
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    RECONCILED = "RECONCILED"
    FAILED = "FAILED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    REJECTED = "REJECTED"


class JiraConflictKind(StrEnum):
    DUPLICATE_REMOTE_MAPPING = "DUPLICATE_REMOTE_MAPPING"
    LOCAL_AND_REMOTE_DIVERGED = "LOCAL_AND_REMOTE_DIVERGED"
    REMOTE_ONLY_ISSUE = "REMOTE_ONLY_ISSUE"
    STATUS_UNMAPPED = "STATUS_UNMAPPED"
    HIERARCHY_MISMATCH = "HIERARCHY_MISMATCH"
    STALE_REMOTE_OBSERVATION = "STALE_REMOTE_OBSERVATION"
    UNKNOWN_WRITE_OUTCOME = "UNKNOWN_WRITE_OUTCOME"
    UNSUPPORTED_REMOTE_TYPE = "UNSUPPORTED_REMOTE_TYPE"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
    EVIDENCE_RECONCILIATION_REQUIRED = "EVIDENCE_RECONCILIATION_REQUIRED"


class JiraVerificationStatus(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class JiraVerification(DomainModel):
    method: str = Field(min_length=1, max_length=191)
    path: str = Field(min_length=1, max_length=1000)
    command: str = Field(min_length=1, max_length=4000)
    status: JiraVerificationStatus


class JiraAcceptanceCriterion(DomainModel):
    criterion_id: str
    statement: str = Field(min_length=1, max_length=4000)
    verification: JiraVerification

    @field_validator("criterion_id")
    @classmethod
    def validate_criterion_id(cls, value: str) -> str:
        if not ACCEPTANCE_ID.fullmatch(value):
            raise ValueError(f"invalid acceptance criterion identifier: {value}")
        return value


class JiraPlanReference(DomainModel):
    plan_id: str
    section_id: str
    authoritative_path: str = Field(min_length=1, max_length=1000)
    line_numbered_path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    line_reference: str = Field(min_length=1, max_length=255)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        if not PLAN_ID.fullmatch(value):
            raise ValueError(f"invalid plan identifier: {value}")
        return value

    @field_validator("section_id")
    @classmethod
    def validate_section_id(cls, value: str) -> str:
        if not PLAN_SECTION_ID.fullmatch(value):
            raise ValueError(f"invalid plan section identifier: {value}")
        return value

    @model_validator(mode="after")
    def validate_lines(self) -> JiraPlanReference:
        if self.end_line < self.start_line:
            raise ValueError("plan reference end_line cannot precede start_line")
        if not self.line_reference.startswith(f"{self.section_id}:L"):
            raise ValueError("plan line reference must begin with its section identifier")
        return self


class JiraRelationship(DomainModel):
    target: str
    type: JiraRelationshipType

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if not ISSUE_ID.fullmatch(value):
            raise ValueError(f"invalid Jira relationship target: {value}")
        return value


class LocalJiraIssue(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    local_id: str
    remote_jira_key: str | None = None
    issue_type: JiraIssueType
    title: str = Field(min_length=5, max_length=1000)
    parent: str | None
    objective: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=4000)
    description: str = Field(min_length=1, max_length=12000)
    scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    source_references: tuple[str, ...]
    plan_references: tuple[JiraPlanReference, ...]
    dependencies: tuple[str, ...]
    blockers: tuple[str, ...]
    relationships: tuple[JiraRelationship, ...]
    upstream_dependencies: tuple[str, ...]
    expected_implementation_artifacts: tuple[str, ...]
    expected_file_locations: tuple[str, ...]
    acceptance_criteria: tuple[JiraAcceptanceCriterion, ...]
    definition_of_done: tuple[str, ...]
    required_tests: tuple[str, ...]
    evidence_required: tuple[str, ...]
    risk_classification: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    security_impact: str = Field(min_length=1, max_length=4000)
    observability_impact: str = Field(min_length=1, max_length=4000)
    rollback_recovery_consideration: str = Field(min_length=1, max_length=4000)
    owner_required_capability: str = Field(min_length=1, max_length=500)
    labels: tuple[str, ...]
    state: JiraLifecycleState
    implementation_state: ImplementationState
    completion_evidence: tuple[str, ...]
    last_observed_remote_state: dict[str, Any] | None = None

    @field_validator("local_id")
    @classmethod
    def validate_local_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @field_validator("remote_jira_key")
    @classmethod
    def validate_remote_key(cls, value: str | None) -> str | None:
        if value is not None and not REMOTE_JIRA_KEY.fullmatch(value):
            raise ValueError(f"invalid remote Jira key: {value}")
        return value

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, value: str | None) -> str | None:
        if value is not None:
            validate_identifier(value, IdentifierKind.ISSUE)
        return value

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            validate_identifier(value, IdentifierKind.REQUIREMENT)
        return values

    @field_validator("source_references")
    @classmethod
    def validate_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            parse_source_reference(value)
        return values

    @field_validator("dependencies", "blockers")
    @classmethod
    def validate_issue_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            validate_identifier(value, IdentifierKind.ISSUE)
        return values

    @field_validator(
        "scope",
        "exclusions",
        "requirement_ids",
        "source_references",
        "dependencies",
        "blockers",
        "upstream_dependencies",
        "expected_implementation_artifacts",
        "expected_file_locations",
        "definition_of_done",
        "required_tests",
        "evidence_required",
        "labels",
        "completion_evidence",
    )
    @classmethod
    def reject_duplicate_scalar_relations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Jira issue relation lists cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_issue_semantics(self) -> LocalJiraIssue:
        expected_type = self.local_id.split("-")[1]
        if expected_type != self.issue_type.value:
            raise ValueError("local Jira identifier type does not match issue_type")
        if self.issue_type is JiraIssueType.EPIC and self.parent is not None:
            raise ValueError("epics cannot have a parent in the restrained local hierarchy")
        if self.issue_type is not JiraIssueType.EPIC and self.parent is None:
            raise ValueError("non-epic Jira work items require a parent")
        if self.parent == self.local_id:
            raise ValueError("Jira work item cannot parent itself")
        if self.local_id in self.dependencies or self.local_id in self.blockers:
            raise ValueError("Jira work item cannot depend on or block itself")
        relation_keys = [(item.type, item.target) for item in self.relationships]
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("Jira relationships cannot contain duplicates")
        if any(item.target == self.local_id for item in self.relationships):
            raise ValueError("Jira work item cannot relate to itself")
        criterion_ids = [item.criterion_id for item in self.acceptance_criteria]
        if not criterion_ids or len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Jira issue acceptance criteria must exist and be uniquely identified")
        if self.state is JiraLifecycleState.DONE and not self.completion_evidence:
            raise ValueError("completed Jira issues require completion evidence")
        return self

    def semantic_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("last_observed_remote_state", None)
        return payload

    def semantic_fingerprint(self) -> str:
        return _digest_payload(self.semantic_payload())

    def traceability_fingerprint(self) -> str:
        return _digest_payload(
            {
                "requirements": self.requirement_ids,
                "sources": self.source_references,
                "plans": [item.model_dump(mode="json") for item in self.plan_references],
                "tests": self.required_tests,
                "evidence_required": self.evidence_required,
                "completion_evidence": self.completion_evidence,
            }
        )


class JiraCommentIntent(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    comment_intent_id: str
    local_id: str
    kind: JiraCommentKind
    body: str = Field(min_length=10, max_length=12000)
    evidence_references: tuple[str, ...] = ()
    decision_references: tuple[str, ...] = ()
    actor_id: str = Field(min_length=3, max_length=191)
    correlation_id: str = Field(min_length=3, max_length=191)
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("comment_intent_id")
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JCOM-"):
            raise ValueError(f"invalid Jira comment intent identifier: {value}")
        return value

    @field_validator("local_id")
    @classmethod
    def validate_issue_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @field_validator("created_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Jira comment timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def reject_noise(self) -> JiraCommentIntent:
        normalized = re.sub(r"\s+", " ", self.body.strip().lower())
        noise_patterns = (
            "started editing ",
            "ran a test",
            "opened another file",
            "opened file ",
        )
        if any(pattern in normalized for pattern in noise_patterns):
            raise ValueError(
                "Jira comments must preserve meaningful project history, not activity noise"
            )
        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError("comment evidence references cannot contain duplicates")
        return self

    @classmethod
    def create(
        cls,
        *,
        local_id: str,
        kind: JiraCommentKind,
        body: str,
        actor_id: str,
        correlation_id: str,
        evidence_references: tuple[str, ...] = (),
        decision_references: tuple[str, ...] = (),
    ) -> JiraCommentIntent:
        identifier = jira_sync_identifier("JCOM", local_id, kind.value, body, *evidence_references)
        return cls(
            comment_intent_id=identifier,
            local_id=local_id,
            kind=kind,
            body=body,
            actor_id=actor_id,
            correlation_id=correlation_id,
            evidence_references=evidence_references,
            decision_references=decision_references,
        )

    def semantic_fingerprint(self) -> str:
        return _digest_payload(
            {
                "local_id": self.local_id,
                "kind": self.kind,
                "body": re.sub(r"\s+", " ", self.body.strip()),
                "evidence": self.evidence_references,
                "decisions": self.decision_references,
            }
        )


class JiraTransitionReadiness(DomainModel):
    local_id: str
    from_state: JiraLifecycleState
    to_state: JiraLifecycleState
    assigned: bool = False
    implementation_evidence_present: bool = False
    branch_present: bool = False
    required_tests_passed: bool = False
    acceptance_criteria_verified: bool = False
    independent_review_complete: bool = False
    blockers_clear: bool = False
    completion_evidence_present: bool = False
    allowed: bool
    reasons: tuple[str, ...] = ()

    @field_validator("local_id")
    @classmethod
    def validate_local_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)


class JiraStatusMapping(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    remote_to_internal: dict[str, JiraLifecycleState]

    @field_validator("remote_to_internal")
    @classmethod
    def validate_mapping(
        cls, value: dict[str, JiraLifecycleState]
    ) -> dict[str, JiraLifecycleState]:
        if not value:
            raise ValueError("Jira status mapping cannot be empty")
        normalized: set[str] = set()
        for name in value:
            key = name.strip().casefold()
            if not key or key in normalized:
                raise ValueError("remote Jira status names must be unique and non-empty")
            normalized.add(key)
        return value

    def normalize(self, remote_status: str) -> JiraLifecycleState | None:
        requested = remote_status.strip().casefold()
        return next(
            (
                state
                for name, state in self.remote_to_internal.items()
                if name.casefold() == requested
            ),
            None,
        )


class RemoteJiraComment(DomainModel):
    comment_id: str
    author_account_id: str | None = None
    body_text: str = Field(min_length=1, max_length=12000)
    created_at_utc: datetime
    updated_at_utc: datetime
    semantic_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("created_at_utc", "updated_at_utc")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("remote Jira timestamps must be timezone-aware")
        return value.astimezone(UTC)


class RemoteJiraLink(DomainModel):
    link_id: str | None = None
    link_type: str = Field(min_length=1, max_length=191)
    outward_key: str
    inward_key: str

    @field_validator("outward_key", "inward_key")
    @classmethod
    def validate_remote_keys(cls, value: str) -> str:
        if not REMOTE_JIRA_KEY.fullmatch(value):
            raise ValueError(f"invalid remote Jira key: {value}")
        return value


class RemoteJiraAttachmentReference(DomainModel):
    attachment_id: str
    filename: str = Field(min_length=1, max_length=1000)
    media_type: str | None = Field(default=None, max_length=191)
    size_bytes: int = Field(ge=0)
    content_url: str | None = Field(default=None, max_length=2048)


class RemoteJiraIssue(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    remote_id: str
    remote_key: str
    local_id: str | None = None
    issue_type_name: str = Field(min_length=1, max_length=191)
    normalized_issue_type: JiraIssueType | None = None
    summary: str = Field(min_length=1, max_length=1000)
    description_text: str = Field(default="", max_length=12000)
    status_name: str = Field(min_length=1, max_length=191)
    normalized_state: JiraLifecycleState | None = None
    parent_remote_key: str | None = None
    labels: tuple[str, ...] = ()
    assignee_account_id: str | None = Field(default=None, max_length=191)
    updated_at_utc: datetime
    version: int | None = Field(default=None, ge=1)
    comments: tuple[RemoteJiraComment, ...] = ()
    links: tuple[RemoteJiraLink, ...] = ()
    attachments: tuple[RemoteJiraAttachmentReference, ...] = ()
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("remote_key", "parent_remote_key")
    @classmethod
    def validate_remote_keys(cls, value: str | None) -> str | None:
        if value is not None and not REMOTE_JIRA_KEY.fullmatch(value):
            raise ValueError(f"invalid remote Jira key: {value}")
        return value

    @field_validator("local_id")
    @classmethod
    def validate_local_id(cls, value: str | None) -> str | None:
        if value is not None:
            validate_identifier(value, IdentifierKind.ISSUE)
        return value

    @field_validator("updated_at_utc")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("remote Jira timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("labels")
    @classmethod
    def reject_duplicate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("remote Jira labels cannot contain duplicates")
        return values

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "remote_key": self.remote_key,
            "local_id": self.local_id,
            "issue_type_name": self.issue_type_name,
            "normalized_issue_type": self.normalized_issue_type,
            "summary": self.summary,
            "description_text": self.description_text,
            "status_name": self.status_name,
            "normalized_state": self.normalized_state,
            "parent_remote_key": self.parent_remote_key,
            "labels": self.labels,
            "assignee_account_id": self.assignee_account_id,
            "version": self.version,
        }

    def semantic_fingerprint(self) -> str:
        return _digest_payload(self.semantic_payload())


class JiraAdapterCapabilities(DomainModel):
    provider: Literal["ATLASSIAN_JIRA_CLOUD", "MOCK_JIRA"]
    api_version: str = Field(min_length=1, max_length=64)
    supports_issue_read: bool = True
    supports_issue_create: bool
    supports_issue_update: bool
    supports_transitions: bool
    supports_comments: bool
    supports_links: bool
    supports_attachments: bool
    supports_webhooks: bool
    pagination_style: Literal["NEXT_PAGE_TOKEN", "START_AT", "MOCK_CURSOR"]
    maximum_page_size: int = Field(ge=1, le=1000)
    discovered_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("discovered_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability timestamp must be timezone-aware")
        return value.astimezone(UTC)


class JiraProjectMetadata(DomainModel):
    project_id: str
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    name: str = Field(min_length=1, max_length=500)
    issue_types: tuple[str, ...]
    statuses: tuple[str, ...]
    components: tuple[str, ...] = ()
    fields: dict[str, str] = Field(default_factory=dict)
    observed_at_utc: datetime = Field(default_factory=utc_now)


class JiraRemoteSnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: str
    source: Literal[JiraSnapshotSource.REMOTE_JIRA, JiraSnapshotSource.IMPORT_BUNDLE]
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    issues: tuple[RemoteJiraIssue, ...]
    complete: bool = True
    next_page_token: str | None = None
    observed_at_utc: datetime = Field(default_factory=utc_now)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JSNAP-"):
            raise ValueError(f"invalid Jira snapshot identifier: {value}")
        return value

    @field_validator("observed_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("snapshot timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_snapshot(self) -> JiraRemoteSnapshot:
        keys = [item.remote_key for item in self.issues]
        if len(keys) != len(set(keys)):
            raise ValueError("remote Jira snapshot contains duplicate issue keys")
        expected = _digest_payload([item.model_dump(mode="json") for item in self.issues])
        if expected != self.fingerprint:
            raise ValueError("remote Jira snapshot fingerprint does not match its issues")
        if self.complete and self.next_page_token is not None:
            raise ValueError("complete remote Jira snapshot cannot retain a next-page token")
        return self

    @classmethod
    def create(
        cls,
        *,
        project_key: str,
        issues: tuple[RemoteJiraIssue, ...],
        source: Literal[
            JiraSnapshotSource.REMOTE_JIRA, JiraSnapshotSource.IMPORT_BUNDLE
        ] = JiraSnapshotSource.REMOTE_JIRA,
        complete: bool = True,
        next_page_token: str | None = None,
        observed_at_utc: datetime | None = None,
    ) -> JiraRemoteSnapshot:
        ordered = tuple(sorted(issues, key=lambda item: item.remote_key))
        fingerprint = _digest_payload([item.model_dump(mode="json") for item in ordered])
        snapshot_id = jira_sync_identifier("JSNAP", project_key, fingerprint)
        return cls(
            snapshot_id=snapshot_id,
            source=source,
            project_key=project_key,
            issues=ordered,
            complete=complete,
            next_page_token=next_page_token,
            observed_at_utc=observed_at_utc or utc_now(),
            fingerprint=fingerprint,
        )


class JiraMirrorBundle(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    board_id: str = Field(min_length=1, max_length=191)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    issues: tuple[LocalJiraIssue, ...]
    issue_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_bundle(self) -> JiraMirrorBundle:
        if self.issue_count != len(self.issues):
            raise ValueError("Jira mirror bundle issue_count is stale")
        identifiers = [item.local_id for item in self.issues]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Jira mirror bundle contains duplicate local IDs")
        expected = _digest_payload([item.model_dump(mode="json") for item in self.issues])
        if expected != self.fingerprint:
            raise ValueError("Jira mirror bundle fingerprint does not match its issues")
        return self


class JiraSyncConflict(DomainModel):
    conflict_id: str
    kind: JiraConflictKind
    local_id: str | None = None
    remote_key: str | None = None
    fields: tuple[str, ...] = ()
    description: str = Field(min_length=1, max_length=4000)
    required_resolution: str = Field(min_length=1, max_length=4000)

    @field_validator("conflict_id")
    @classmethod
    def validate_conflict_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JCON-"):
            raise ValueError(f"invalid Jira conflict identifier: {value}")
        return value

    @field_validator("local_id")
    @classmethod
    def validate_local_id(cls, value: str | None) -> str | None:
        if value is not None:
            validate_identifier(value, IdentifierKind.ISSUE)
        return value

    @field_validator("remote_key")
    @classmethod
    def validate_remote_key(cls, value: str | None) -> str | None:
        if value is not None and not REMOTE_JIRA_KEY.fullmatch(value):
            raise ValueError(f"invalid remote Jira key: {value}")
        return value


class JiraSyncOperation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    operation_id: str
    operation_type: JiraSyncOperationType
    local_id: str | None = None
    remote_key: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)
    expected_remote_version: int | None = Field(default=None, ge=1)
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_remote_write: bool
    requires_human_approval: bool = False
    state: JiraOperationState = JiraOperationState.PLANNED

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JOP-"):
            raise ValueError(f"invalid Jira operation identifier: {value}")
        return value

    @field_validator("local_id")
    @classmethod
    def validate_local_id(cls, value: str | None) -> str | None:
        if value is not None:
            validate_identifier(value, IdentifierKind.ISSUE)
        return value

    @field_validator("remote_key")
    @classmethod
    def validate_remote_key(cls, value: str | None) -> str | None:
        if value is not None and not REMOTE_JIRA_KEY.fullmatch(value):
            raise ValueError(f"invalid remote Jira key: {value}")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> JiraSyncOperation:
        expected = _digest_payload(self.payload)
        if self.request_fingerprint != expected:
            raise ValueError("Jira operation request fingerprint does not match its payload")
        write_operations = {
            JiraSyncOperationType.CREATE_REMOTE_ISSUE,
            JiraSyncOperationType.UPDATE_REMOTE_FIELDS,
            JiraSyncOperationType.TRANSITION_REMOTE_ISSUE,
            JiraSyncOperationType.ADD_REMOTE_COMMENT,
            JiraSyncOperationType.CREATE_REMOTE_LINK,
        }
        if (self.operation_type in write_operations) != self.requires_remote_write:
            raise ValueError("Jira operation write classification is inconsistent")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_type: JiraSyncOperationType,
        payload: dict[str, Any],
        local_id: str | None,
        remote_key: str | None,
        expected_remote_version: int | None = None,
        requires_human_approval: bool = False,
    ) -> JiraSyncOperation:
        fingerprint = _digest_payload(payload)
        identity_subject = local_id or remote_key or "project"
        operation_id = jira_sync_identifier(
            "JOP", operation_type.value, identity_subject, fingerprint
        )
        return cls(
            operation_id=operation_id,
            operation_type=operation_type,
            local_id=local_id,
            remote_key=remote_key,
            idempotency_key=f"jira:{operation_id.lower()}",
            expected_remote_version=expected_remote_version,
            request_fingerprint=fingerprint,
            payload=payload,
            requires_remote_write=operation_type
            in {
                JiraSyncOperationType.CREATE_REMOTE_ISSUE,
                JiraSyncOperationType.UPDATE_REMOTE_FIELDS,
                JiraSyncOperationType.TRANSITION_REMOTE_ISSUE,
                JiraSyncOperationType.ADD_REMOTE_COMMENT,
                JiraSyncOperationType.CREATE_REMOTE_LINK,
            },
            requires_human_approval=requires_human_approval,
        )


class JiraReconciliationPlan(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_id: str
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    authority_mode: JiraAuthorityMode
    local_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    remote_snapshot_id: str
    remote_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    operations: tuple[JiraSyncOperation, ...]
    conflicts: tuple[JiraSyncConflict, ...]
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JPLAN-"):
            raise ValueError(f"invalid Jira reconciliation plan identifier: {value}")
        return value

    @field_validator("remote_snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JSNAP-"):
            raise ValueError(f"invalid Jira snapshot identifier: {value}")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> JiraReconciliationPlan:
        operation_ids = [item.operation_id for item in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("Jira reconciliation plan contains duplicate operations")
        conflict_ids = [item.conflict_id for item in self.conflicts]
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ValueError("Jira reconciliation plan contains duplicate conflicts")
        return self

    @property
    def remote_write_count(self) -> int:
        return sum(1 for item in self.operations if item.requires_remote_write)


class JiraSyncReceipt(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: str
    plan_id: str
    mode: JiraSyncMode
    result: Literal["DRY_RUN", "APPLIED", "PARTIAL", "RECONCILIATION_REQUIRED", "REJECTED"]
    applied_operation_ids: tuple[str, ...] = ()
    failed_operation_ids: tuple[str, ...] = ()
    unknown_outcome_operation_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    remote_snapshot_id_after: str | None = None
    actor_id: str = Field(min_length=3, max_length=191)
    correlation_id: str = Field(min_length=3, max_length=191)
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JREC-"):
            raise ValueError(f"invalid Jira receipt identifier: {value}")
        return value

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        if not JIRA_SYNC_ID.fullmatch(value) or not value.startswith("JPLAN-"):
            raise ValueError(f"invalid Jira reconciliation plan identifier: {value}")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> JiraSyncReceipt:
        buckets = (
            set(self.applied_operation_ids),
            set(self.failed_operation_ids),
            set(self.unknown_outcome_operation_ids),
        )
        if any(
            left & right for index, left in enumerate(buckets) for right in buckets[index + 1 :]
        ):
            raise ValueError("Jira operation result buckets cannot overlap")
        if self.mode is JiraSyncMode.DRY_RUN and self.applied_operation_ids:
            raise ValueError("dry-run Jira receipt cannot claim applied operations")
        if self.unknown_outcome_operation_ids and self.result != "RECONCILIATION_REQUIRED":
            raise ValueError("unknown outcomes require reconciliation")
        return self
