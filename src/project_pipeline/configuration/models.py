from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EnvironmentName(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"
    RECOVERY = "recovery"
    SYNTHETIC = "synthetic"


class ExternalWriteMode(StrEnum):
    DENY = "DENY"
    DRY_RUN = "DRY_RUN"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class LogFormat(StrEnum):
    JSON = "JSON"
    TEXT = "TEXT"


class TelemetryExporter(StrEnum):
    NONE = "NONE"
    OTLP_HTTP = "OTLP_HTTP"


class PersistenceBackend(StrEnum):
    SQLITE_LOCAL = "SQLITE_LOCAL"
    POSTGRESQL = "POSTGRESQL"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class SecretReference(StrictModel):
    """Reference to secret material; the secret value is never stored in configuration."""

    reference: Annotated[str, Field(min_length=7, max_length=512)]

    @model_validator(mode="before")
    @classmethod
    def parse_string(cls, value: object) -> object:
        return {"reference": value} if isinstance(value, str) else value

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        scheme, separator, target = value.partition("://")
        if separator != "://" or scheme not in {"env", "file", "dpapi", "gh-auth"}:
            raise ValueError("secret references must use env://, file://, dpapi://, or gh-auth://")
        if not target or target.strip() != target:
            raise ValueError("secret reference target must be non-empty and trimmed")
        if any(character in target for character in ("\x00", "\n", "\r")):
            raise ValueError("secret reference target contains an invalid character")
        if scheme == "env" and not target.replace("_", "").isalnum():
            raise ValueError("environment secret reference contains invalid characters")
        if scheme == "file" and (Path(target).is_absolute() or target.startswith(("/", "\\"))):
            raise ValueError("file secret references must be repository-relative")
        if scheme == "dpapi" and not (target.replace("_", "").replace("-", "").isalnum()):
            raise ValueError("DPAPI secret reference contains invalid characters")
        if scheme == "gh-auth" and target != "default":
            raise ValueError("gh-auth secret reference target must be default")
        return value

    @property
    def scheme(self) -> str:
        return self.reference.partition("://")[0]

    @property
    def target(self) -> str:
        return self.reference.partition("://")[2]


class RuntimePaths(StrictModel):
    data_dir: Annotated[Path, Field(default=".local/data")]
    state_dir: Annotated[Path, Field(default=".local/state")]
    evidence_dir: Annotated[Path, Field(default=".local/evidence")]
    artifact_dir: Annotated[Path, Field(default=".local/artifacts")]
    cache_dir: Annotated[Path, Field(default=".local/cache")]
    log_dir: Annotated[Path, Field(default=".local/logs")]
    create_on_boot: bool = True

    @field_validator(
        "data_dir", "state_dir", "evidence_dir", "artifact_dir", "cache_dir", "log_dir"
    )
    @classmethod
    def reject_blank_paths(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("configured paths cannot be blank")
        return value


class LoggingSettings(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: LogFormat = LogFormat.JSON
    service_name: str = "project-pipeline"
    include_source: bool = False
    include_process: bool = True
    include_thread: bool = False
    redacted_fields: tuple[str, ...] = (
        "api_key",
        "authorization",
        "client_secret",
        "cookie",
        "password",
        "private_key",
        "secret",
        "token",
    )

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("logging service name cannot be blank")
        return value


class TelemetrySettings(StrictModel):
    enabled: bool = False
    exporter: TelemetryExporter = TelemetryExporter.NONE
    otlp_endpoint: str | None = None
    service_name: str = "project-pipeline"
    service_namespace: str = "project-pipeline"

    @model_validator(mode="after")
    def validate_exporter(self) -> TelemetrySettings:
        if not self.enabled and self.exporter is not TelemetryExporter.NONE:
            raise ValueError("telemetry exporter must be NONE while telemetry is disabled")
        if self.exporter is TelemetryExporter.OTLP_HTTP and not self.otlp_endpoint:
            raise ValueError("OTLP_HTTP exporter requires otlp_endpoint")
        return self


class SecuritySettings(StrictModel):
    external_writes_default: ExternalWriteMode = ExternalWriteMode.DENY
    require_explicit_approval: bool = True

    @model_validator(mode="after")
    def enforce_approval_boundary(self) -> SecuritySettings:
        if (
            self.external_writes_default is ExternalWriteMode.REQUIRE_APPROVAL
            and not self.require_explicit_approval
        ):
            raise ValueError("external writes cannot bypass explicit approval")
        return self


class PersistenceSettings(StrictModel):
    backend: PersistenceBackend = PersistenceBackend.SQLITE_LOCAL
    sqlite_path: Annotated[Path, Field(default=".local/state/project_pipeline.db")]
    postgresql_dsn: SecretReference | None = None
    migration_catalog: Annotated[Path, Field(default="database/MIGRATION_CATALOG.json")]
    auto_migrate: bool = True

    @field_validator("sqlite_path", "migration_catalog")
    @classmethod
    def reject_blank_paths(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("persistence paths cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_backend(self) -> PersistenceSettings:
        if self.backend is PersistenceBackend.POSTGRESQL and self.postgresql_dsn is None:
            raise ValueError("POSTGRESQL persistence requires postgresql_dsn")
        if self.backend is PersistenceBackend.SQLITE_LOCAL and self.postgresql_dsn is not None:
            raise ValueError("SQLITE_LOCAL persistence cannot include postgresql_dsn")
        return self


class IntegrationSettings(StrictModel):
    jira_base_url: str | None = None
    jira_user_email: str | None = None
    jira_api_token: SecretReference | None = None
    github_token: SecretReference | None = None
    aws_profile: str | None = None

    @field_validator("jira_base_url")
    @classmethod
    def validate_jira_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("jira_base_url must be an absolute HTTP or HTTPS URL")
        return value.rstrip("/")

    @field_validator("jira_user_email", "aws_profile")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RuntimeSettings(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = "PROJECT-PIPELINE"
    project_name: str = "ProjectPipeline"
    profile: str = "local"
    environment: EnvironmentName = EnvironmentName.DEVELOPMENT
    paths: RuntimePaths = Field(default_factory=lambda: RuntimePaths.model_validate({}))
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    persistence: PersistenceSettings = Field(
        default_factory=lambda: PersistenceSettings.model_validate({})
    )
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)

    @field_validator("project_id", "project_name", "profile")
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project identity and profile values cannot be blank")
        return value

    def resolve_path(self, root: Path, configured: Path) -> Path:
        return configured.resolve() if configured.is_absolute() else (root / configured).resolve()

    def database_path(self, root: Path) -> Path:
        if self.persistence.backend is not PersistenceBackend.SQLITE_LOCAL:
            raise ValueError("database_path is only available for SQLITE_LOCAL persistence")
        return self.resolve_path(root, self.persistence.sqlite_path)

    def migration_catalog_path(self, root: Path) -> Path:
        return self.resolve_path(root, self.persistence.migration_catalog)

    def runtime_paths(self, root: Path) -> dict[str, Path]:
        return {
            name: self.resolve_path(root, value)
            for name, value in {
                "data_dir": self.paths.data_dir,
                "state_dir": self.paths.state_dir,
                "evidence_dir": self.paths.evidence_dir,
                "artifact_dir": self.paths.artifact_dir,
                "cache_dir": self.paths.cache_dir,
                "log_dir": self.paths.log_dir,
            }.items()
        }
