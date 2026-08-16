import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.domain.security import (
    AuthorityCapability,
    CapabilityGrant,
    SecretBackendKind,
    SecretCapabilityReference,
    security_identifier,
)
from project_pipeline.security.backends import (
    AgeSecretBackend,
    EnvFileSecretBackend,
    OpenBaoSecretBackend,
    SopsSecretBackend,
)
from project_pipeline.security.secrets import SecretsBroker
from project_pipeline.upstream_integrations.common import UpstreamIntegrationError
from project_pipeline.upstream_integrations.security import AgeAdapter, SopsAdapter


def grant(identity, now):
    return CapabilityGrant(
        grant_id=security_identifier("GRANT", identity, "secret"),
        identity_id=identity,
        capability=AuthorityCapability.ACCESS_SECRET,
        project_id="P",
        target_prefix="svc",
        environment="prod",
        operation_class="connect",
        issued_by="human",
        issued_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )


def ref(kind, reference):
    return SecretCapabilityReference(
        secret_ref_id=security_identifier("SREF", kind.value, reference),
        logical_name="db",
        backend=kind,
        reference=reference,
        allowed_operations=("connect",),
        allowed_target_prefixes=("svc",),
    )


def test_secret_lease_scope_and_runtime_plaintext_not_persisted():
    now = datetime.now(UTC)
    identity = security_identifier("IDENT", "agent")
    r = ref(SecretBackendKind.ENVIRONMENT, "env://TOKEN")
    broker = SecretsBroker(
        backends={"ENVIRONMENT": EnvFileSecretBackend(Path("."), {"TOKEN": "super-secret"})}
    )
    broker.register_reference(r)
    lease = broker.issue_lease(
        secret_ref_id=r.secret_ref_id,
        identity_id=identity,
        project_id="P",
        target="svc/db",
        operation="connect",
        issued_by="human",
        grant=grant(identity, now),
        now=now,
    )
    secret = broker.materialize(
        lease.lease_id, identity_id=identity, target="svc/db", operation="connect", now=now
    )
    assert secret.value == "super-secret"
    assert "super-secret" not in repr(secret) and "super-secret" not in str(secret.metadata())
    assert secret.metadata()["plaintext_persisted"] is False


def test_secret_lease_rejects_wrong_target_and_expiry():
    now = datetime.now(UTC)
    identity = security_identifier("IDENT", "agent2")
    r = ref(SecretBackendKind.ENVIRONMENT, "env://TOKEN")
    b = SecretsBroker(backends={})
    b.register_reference(r)
    with pytest.raises(PermissionError):
        b.issue_lease(
            secret_ref_id=r.secret_ref_id,
            identity_id=identity,
            project_id="P",
            target="other",
            operation="connect",
            issued_by="h",
            grant=grant(identity, now),
            now=now,
        )
    lease = b.issue_lease(
        secret_ref_id=r.secret_ref_id,
        identity_id=identity,
        project_id="P",
        target="svc",
        operation="connect",
        issued_by="h",
        grant=grant(identity, now),
        ttl_seconds=1,
        now=now,
    )
    with pytest.raises(PermissionError):
        b.materialize(
            lease.lease_id,
            identity_id=identity,
            target="svc",
            operation="connect",
            now=now + timedelta(seconds=2),
        )


def test_sops_backend_materializes_with_fake_runner(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("ENC")

    def runner(argv, cwd, stdin, timeout, env):
        return subprocess.CompletedProcess(argv, 0, "value\n", "")

    a = SopsAdapter(runner=runner)
    b = SopsSecretBackend(tmp_path, a)
    r = ref(SecretBackendKind.SOPS, 'sops://s.yaml#data["token"]')
    assert b.resolve(r) == "value"


def test_age_backend_uses_age_kind(tmp_path):
    f = tmp_path / "s.age"
    f.write_text("ENC")
    identity = tmp_path / "id"
    identity.write_text("AGE-SECRET-KEY-REDACTED")

    def runner(argv, cwd, stdin, timeout, env):
        return subprocess.CompletedProcess(argv, 0, "age-value\n", "")

    b = AgeSecretBackend(tmp_path, identity, AgeAdapter(runner=runner))
    r = ref(SecretBackendKind.AGE, "age-file://s.age")
    assert b.resolve(r) == "age-value"


def test_openbao_requires_network_and_supports_kv_v2():
    def transport(method, url, headers):
        return 200, '{"data":{"data":{"token":"vault-value"}}}'

    r = ref(SecretBackendKind.OPENBAO, "openbao://secret/data/app#token")
    b = OpenBaoSecretBackend("https://vault.example", lambda: "runtime-token", transport=transport)
    with pytest.raises(UpstreamIntegrationError):
        b.resolve(r)
    b.allow_network = True
    assert b.resolve(r) == "vault-value"
