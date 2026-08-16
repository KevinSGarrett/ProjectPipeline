# Docker Packaging

The Dockerfile deliberately has **no default base image**. `PROJECT_PIPELINE_BASE_IMAGE` must be supplied as an immutable image digest reference by the deployment authority. The container runs as UID 10001, drops Linux capabilities through the Compose profile, uses a read-only filesystem, and binds the published port to localhost by default.

Docker is not installed in the Pass 24 build environment, so these assets are **source implemented but runtime not qualified**. A later target-specific qualification must execute image build, SBOM/vulnerability scan, startup, health/authentication checks, shutdown, upgrade, rollback, and cleanup before claiming container deployment readiness.
