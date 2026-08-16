from __future__ import annotations

from datetime import UTC, datetime

from project_pipeline.domain.lifecycle import (
    DataClassification,
    EnvironmentLease,
    EnvironmentType,
    TestDataAsset,
)


class EnvironmentManager:
    def validate_lease(self, lease: EnvironmentLease) -> dict[str, object]:
        if (
            lease.environment_type in {EnvironmentType.PREVIEW, EnvironmentType.TEMPORARY_TEST}
            and lease.ttl_seconds is None
        ):
            raise ValueError("temporary/preview environments require ttl_seconds")
        if lease.data_classification in {
            DataClassification.PRODUCTION,
            DataClassification.PRODUCTION_DERIVED,
        }:
            if not lease.production_copy_explicitly_permitted:
                raise PermissionError(
                    "production or production-derived data requires explicit permission"
                )
            if not lease.transformation_verified:
                raise PermissionError(
                    "production-derived autonomous test data requires verified transformation"
                )
        return {
            "environment_id": lease.environment_id,
            "namespace": lease.namespace,
            "isolated": True,
            "destructive_shared_test_target": False,
        }

    def leak_status(
        self, lease: EnvironmentLease, *, now: datetime | None = None
    ) -> dict[str, object]:
        now = now or datetime.now(UTC)
        if lease.ttl_seconds is None:
            return {"leaked": False, "cleanup_plan_required": False}
        age = (now - lease.created_at_utc).total_seconds()
        leaked = age > lease.ttl_seconds
        return {
            "leaked": leaked,
            "cleanup_plan_required": leaked,
            "destructive_cleanup_authorized": False,
        }


class TestDataLifecycleManager:
    def validate_asset(self, asset: TestDataAsset) -> dict[str, object]:
        if (
            asset.classification
            in {
                DataClassification.PRODUCTION,
                DataClassification.PRODUCTION_DERIVED,
                DataClassification.SENSITIVE_TEST,
            }
            and not asset.masking_verified
        ):
            raise PermissionError(
                "sensitive/production-derived test data requires verified masking/transformation"
            )
        return {
            "asset_id": asset.asset_id,
            "provenance_recorded": bool(asset.provenance),
            "destruction_is_policy_gated": True,
            "retention_days": asset.retention_days,
        }
