from __future__ import annotations

import json
import os
import runpy
import socket
import sqlite3
import subprocess
import tempfile
import unittest
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from project_pipeline.cli import _load_configuration, _secret_resolver
from project_pipeline.configuration import (
    ConfigurationError,
    SecretReference,
    SecretResolutionError,
    SecretResolver,
    load_runtime_configuration,
    parse_selected_env_file,
    runtime_configuration_schema,
    validate_runtime_configuration_files,
)
from project_pipeline.configuration.campaign_environment import (
    campaign_credential_envelope_scope,
    campaign_runtime_environment_from_process,
    limited_campaign_subprocess_environment,
    load_campaign_runtime_environment,
    validate_campaign_runtime_binding,
)
from project_pipeline.configuration.secrets import (
    CampaignSecretAccessLease,
    _dpapi_unprotect,
    build_dpapi_secret_envelope,
    current_windows_principal_sid,
    issue_campaign_secret_access_lease,
    protect_dpapi_secret,
)

ROOT = Path(__file__).resolve().parents[1]


def _campaign_scope(
    *,
    machine_id: str = "COMFY-V4-CPU-01",
    identity_id: str = "S-1-5-21-1000",
    campaign_id: str = "QCAMP-C16B-TEST",
    candidate_sha: str = "a" * 40,
    candidate_tree: str = "b" * 40,
    scheduler_lease_id: str = "CLEASE-C16B-TEST",
    fence_token: str = "CFENCE-C16B-TEST",
    expires_at_utc: str = "2099-01-01T00:00:00+00:00",
) -> dict[str, str]:
    return {
        "project_id": "PROJECT-PIPELINE",
        "cycle_id": "CYCLE-16-B",
        "machine_id": machine_id,
        "identity_id": identity_id,
        "campaign_id": campaign_id,
        "candidate_sha": candidate_sha,
        "candidate_tree": candidate_tree,
        "scheduler_lease_id": scheduler_lease_id,
        "fence_token": fence_token,
        "expires_at_utc": expires_at_utc,
    }


def _campaign_runtime_text(*, expiry: datetime, deadline: datetime) -> str:
    scope = _campaign_scope(expires_at_utc=expiry.isoformat())
    values = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "worker@example.test",
        "JIRA_API_TOKEN_REF": "dpapi://C16B_JIRA_TOKEN",
        "GITHUB_TOKEN_REF": "dpapi://C16B_GITHUB_TOKEN",
        "CAMPAIGN_PROJECT_ID": scope["project_id"],
        "CAMPAIGN_CYCLE_ID": scope["cycle_id"],
        "CAMPAIGN_MACHINE_ID": scope["machine_id"],
        "CAMPAIGN_PRINCIPAL_SID": scope["identity_id"],
        "CAMPAIGN_ID": scope["campaign_id"],
        "CAMPAIGN_CANDIDATE_SHA": scope["candidate_sha"],
        "CAMPAIGN_CANDIDATE_TREE": scope["candidate_tree"],
        "CAMPAIGN_SCHEDULER_LEASE_ID": scope["scheduler_lease_id"],
        "CAMPAIGN_FENCE_TOKEN": scope["fence_token"],
        "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC": scope["expires_at_utc"],
        "CAMPAIGN_DEADLINE_AT_UTC": deadline.isoformat(),
        "CAMPAIGN_DATABASE": "C:/campaign.sqlite3",
    }
    return "".join(f"{key}={value}\n" for key, value in values.items())


def _write_security_policy(root: Path, *, maximum_seconds: int = 900) -> None:
    policy = root / "config" / "security_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(json.dumps({"secret_lease_max_seconds": maximum_seconds}), encoding="utf-8")


class ConfigurationTests(unittest.TestCase):
    def test_cli_secret_resolver_uses_explicit_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "credentials.env"
            env_file.write_text("PP_TEST_CLI_SECRET=resolved-from-file\n", encoding="utf-8")
            args = Namespace(root=root, env_file=env_file)
            with patch.dict("os.environ", {}, clear=True):
                value = _secret_resolver(args).resolve(
                    SecretReference(reference="env://PP_TEST_CLI_SECRET")
                )
            self.assertEqual(value, "resolved-from-file")

    def test_campaign_cli_configuration_excludes_mutable_default_environment_file(self) -> None:
        campaign_environment = {
            line.split("=", 1)[0]: line.split("=", 1)[1]
            for line in _campaign_runtime_text(
                expiry=datetime.now(UTC) + timedelta(days=6),
                deadline=datetime.now(UTC) + timedelta(hours=101),
            ).splitlines()
            if line
        }
        args = Namespace(
            root=ROOT,
            profile=None,
            config_file=None,
            env_file=ROOT / ".env",
            overrides=(),
        )
        expected = object()
        with (
            patch(
                "project_pipeline.cli.campaign_runtime_environment_from_process",
                return_value=campaign_environment,
            ),
            patch("project_pipeline.cli.load_runtime_configuration", return_value=expected) as load,
        ):
            self.assertIs(_load_configuration(args), expected)
        self.assertEqual(load.call_args.kwargs["env_file"], None)
        self.assertFalse(load.call_args.kwargs["include_default_env_file"])
        self.assertEqual(load.call_args.kwargs["environment"], campaign_environment)

    def test_campaign_process_environment_is_fail_closed_and_allowlisted(self) -> None:
        environment = {
            line.split("=", 1)[0]: line.split("=", 1)[1]
            for line in _campaign_runtime_text(
                expiry=datetime.now(UTC) + timedelta(days=6),
                deadline=datetime.now(UTC) + timedelta(hours=101),
            ).splitlines()
            if line
        }
        environment["UNRELATED_SECRET"] = "must-not-be-retained"
        values = campaign_runtime_environment_from_process(ROOT, source=environment)
        self.assertIsNotNone(values)
        assert values is not None
        self.assertNotIn("UNRELATED_SECRET", values)
        del environment["CAMPAIGN_DATABASE"]
        with self.assertRaisesRegex(ConfigurationError, "database binding"):
            campaign_runtime_environment_from_process(ROOT, source=environment)

    def test_campaign_runtime_binding_requires_matching_checkout_and_campaign_row(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "show", "-s", "--format=%T", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "campaign.sqlite3"
            scope = _campaign_scope(
                candidate_sha=head,
                candidate_tree=tree,
                expires_at_utc=(datetime.now(UTC) + timedelta(days=6)).isoformat(),
            )
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """
                    CREATE TABLE campaign_runs (
                        campaign_id TEXT, integrated_sha TEXT, integrated_tree TEXT,
                        fence TEXT, lease_id TEXT, status TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO campaign_runs VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        scope["campaign_id"],
                        scope["candidate_sha"],
                        scope["candidate_tree"],
                        scope["fence_token"],
                        scope["scheduler_lease_id"],
                        "ATTESTED",
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            values = {
                "JIRA_BASE_URL": "https://example.atlassian.net",
                "JIRA_USER_EMAIL": "worker@example.test",
                "JIRA_API_TOKEN_REF": "dpapi://C16B_JIRA_TOKEN",
                "GITHUB_TOKEN_REF": "dpapi://C16B_GITHUB_TOKEN",
                "CAMPAIGN_PROJECT_ID": scope["project_id"],
                "CAMPAIGN_CYCLE_ID": scope["cycle_id"],
                "CAMPAIGN_MACHINE_ID": scope["machine_id"],
                "CAMPAIGN_PRINCIPAL_SID": scope["identity_id"],
                "CAMPAIGN_ID": scope["campaign_id"],
                "CAMPAIGN_CANDIDATE_SHA": scope["candidate_sha"],
                "CAMPAIGN_CANDIDATE_TREE": scope["candidate_tree"],
                "CAMPAIGN_SCHEDULER_LEASE_ID": scope["scheduler_lease_id"],
                "CAMPAIGN_FENCE_TOKEN": scope["fence_token"],
                "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC": scope["expires_at_utc"],
                "CAMPAIGN_DEADLINE_AT_UTC": (datetime.now(UTC) + timedelta(hours=101)).isoformat(),
                "CAMPAIGN_DATABASE": str(database),
            }
            self.assertEqual(validate_campaign_runtime_binding(ROOT, values), scope)
            values["CAMPAIGN_CANDIDATE_TREE"] = "f" * 40
            with self.assertRaisesRegex(ConfigurationError, "checked-out candidate"):
                validate_campaign_runtime_binding(ROOT, values)

    def test_selected_environment_parser_retains_only_requested_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "JIRA_BASE_URL=https://example.atlassian.net\n"
                "JIRA_USER_EMAIL=worker@example.test\n"
                "JIRA_API_TOKEN=selected-token\n"
                "UNRELATED_SECRET=must-not-be-retained\n",
                encoding="utf-8",
            )
            values = parse_selected_env_file(
                env_file, {"JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN"}
            )
        self.assertEqual(
            values,
            {
                "JIRA_BASE_URL": "https://example.atlassian.net",
                "JIRA_USER_EMAIL": "worker@example.test",
                "JIRA_API_TOKEN": "selected-token",
            },
        )
        self.assertNotIn("UNRELATED_SECRET", values)

    def test_layer_precedence_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "override.json"
            override.write_text(
                json.dumps({"logging": {"level": "WARNING"}, "paths": {"data_dir": "file"}}),
                encoding="utf-8",
            )
            configuration = load_runtime_configuration(
                ROOT,
                profile="local",
                config_file=override,
                environment={
                    "PROJECT_PIPELINE__LOGGING__LEVEL": "ERROR",
                    "PROJECT_PIPELINE__PATHS__DATA_DIR": "environment",
                },
                overrides=("logging.level=DEBUG", "paths.data_dir=override"),
            )
        self.assertEqual(configuration.settings.logging.level, "DEBUG")
        self.assertEqual(str(configuration.settings.paths.data_dir), "override")
        self.assertIn("PROJECT_PIPELINE__LOGGING__LEVEL", configuration.environment_keys)
        self.assertEqual(configuration.override_keys, ("logging.level", "paths.data_dir"))

    def test_unknown_configuration_key_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_runtime_configuration(
                ROOT,
                profile="local",
                environment={"PROJECT_PIPELINE__UNKNOWN__VALUE": "1"},
            )

    def test_secret_references_are_not_materialized_in_effective_configuration(self) -> None:
        configuration = load_runtime_configuration(
            ROOT,
            profile="local",
            environment={"GITHUB_TOKEN_REF": "env://EXAMPLE_TOKEN"},
        )
        redacted = configuration.redacted_dict()
        self.assertEqual(redacted["integrations"]["github_token"], "env://EXAMPLE_TOKEN")
        self.assertNotIn("secret-value", json.dumps(redacted))

    def test_secret_resolver_supports_environment_and_confined_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_file = root / "private" / "token.txt"
            secret_file.parent.mkdir()
            secret_file.write_text("file-value\n", encoding="utf-8")
            resolver = SecretResolver(root, {"TOKEN": "environment-value"})
            self.assertEqual(
                resolver.resolve(SecretReference(reference="env://TOKEN")), "environment-value"
            )
            self.assertEqual(
                resolver.resolve(SecretReference(reference="file://private/token.txt")),
                "file-value",
            )

    def test_secret_resolver_rejects_root_escape_and_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            resolver = SecretResolver(root, {})
            with self.assertRaises(SecretResolutionError):
                resolver.resolve(SecretReference(reference="file://../outside.txt"))
            with self.assertRaises(SecretResolutionError):
                resolver.resolve(SecretReference(reference="env://MISSING"))

    def test_secret_resolver_uses_github_cli_reference_without_environment_token(self) -> None:
        completed = subprocess.CompletedProcess(["gh", "auth", "token"], 0, "token-from-cli\n", "")
        with patch(
            "project_pipeline.configuration.secrets.subprocess.run", return_value=completed
        ) as run:
            value = SecretResolver(Path("."), {}).resolve(
                SecretReference(reference="gh-auth://default")
            )
        self.assertEqual(value, "token-from-cli")
        self.assertEqual(run.call_args.args[0], ["gh", "auth", "token"])

    def test_campaign_runtime_environment_is_nonsecret_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "campaign-runtime.env"
            env_file.write_text(
                _campaign_runtime_text(
                    expiry=datetime.now(UTC) + timedelta(days=6),
                    deadline=datetime.now(UTC) + timedelta(hours=101),
                ),
                encoding="utf-8",
            )
            values = load_campaign_runtime_environment(ROOT, env_file)
            environment = limited_campaign_subprocess_environment(
                ROOT,
                env_file,
                source={
                    "PATH": "safe-path",
                    "SYSTEMROOT": "safe-root",
                    "JIRA_API_TOKEN": "must-not-reach-recovery",
                    "UNRELATED_SECRET": "no",
                },
            )
        self.assertEqual(values["JIRA_API_TOKEN_REF"], "dpapi://C16B_JIRA_TOKEN")
        self.assertEqual(environment["GITHUB_TOKEN_REF"], "dpapi://C16B_GITHUB_TOKEN")
        self.assertNotIn("UNRELATED_SECRET", environment)
        self.assertNotIn("JIRA_API_TOKEN", environment)

    def test_campaign_runtime_environment_rejects_non_campaign_secret_schemes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "campaign-runtime.env"
            env_file.write_text(
                _campaign_runtime_text(
                    expiry=datetime.now(UTC) + timedelta(days=6),
                    deadline=datetime.now(UTC) + timedelta(hours=101),
                )
                .replace(
                    "JIRA_API_TOKEN_REF=dpapi://C16B_JIRA_TOKEN", "JIRA_API_TOKEN_REF=env://MUTABLE"
                )
                .replace(
                    "GITHUB_TOKEN_REF=dpapi://C16B_GITHUB_TOKEN",
                    "GITHUB_TOKEN_REF=gh-auth://default",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_campaign_runtime_environment(ROOT, env_file)

    def test_campaign_runtime_environment_rejects_ambient_github_cli_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "campaign-runtime.env"
            env_file.write_text(
                _campaign_runtime_text(
                    expiry=datetime.now(UTC) + timedelta(days=6),
                    deadline=datetime.now(UTC) + timedelta(hours=101),
                ).replace(
                    "GITHUB_TOKEN_REF=dpapi://C16B_GITHUB_TOKEN",
                    "GITHUB_TOKEN_REF=gh-auth://default",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_campaign_runtime_environment(ROOT, env_file)

    def test_campaign_envelope_admission_window_is_not_reapplied_during_recovery(self) -> None:
        scope = _campaign_scope(
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=108)).isoformat()
        )
        values = {
            "CAMPAIGN_PROJECT_ID": scope["project_id"],
            "CAMPAIGN_CYCLE_ID": scope["cycle_id"],
            "CAMPAIGN_MACHINE_ID": scope["machine_id"],
            "CAMPAIGN_PRINCIPAL_SID": scope["identity_id"],
            "CAMPAIGN_ID": scope["campaign_id"],
            "CAMPAIGN_CANDIDATE_SHA": scope["candidate_sha"],
            "CAMPAIGN_CANDIDATE_TREE": scope["candidate_tree"],
            "CAMPAIGN_SCHEDULER_LEASE_ID": scope["scheduler_lease_id"],
            "CAMPAIGN_FENCE_TOKEN": scope["fence_token"],
            "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC": scope["expires_at_utc"],
        }
        self.assertEqual(
            campaign_credential_envelope_scope(values)["scheduler_lease_id"], "CLEASE-C16B-TEST"
        )
        with self.assertRaises(ConfigurationError):
            campaign_credential_envelope_scope(values, require_fresh_campaign_window=True)

    def test_campaign_runtime_environment_requires_lease_to_cover_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "campaign-runtime.env"
            env_file.write_text(
                _campaign_runtime_text(
                    expiry=datetime.now(UTC) + timedelta(days=5),
                    deadline=datetime.now(UTC) + timedelta(days=6),
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_campaign_runtime_environment(ROOT, env_file)

    def test_dpapi_revocation_requires_scope_and_persists_reconciliation(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        scope = _campaign_scope()
        reference = SecretReference(reference="dpapi://C16B_JIRA_TOKEN")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / ".local" / "secure-secrets" / "dpapi" / "C16B_JIRA_TOKEN.json"
            destination.parent.mkdir(parents=True)
            destination.write_text(
                json.dumps(
                    {
                        "reference": reference.reference,
                        "scope": scope,
                        "ciphertext_base64": "not-secret-test-data",
                    }
                ),
                encoding="utf-8",
            )
            receipt_path = root / ".local" / "evidence" / "revocation.json"
            receipt = script["_revoke"](root, reference, scope, receipt_path)
            self.assertTrue(receipt["revoked"])
            self.assertFalse(destination.exists())
            self.assertEqual(
                json.loads(receipt_path.read_text(encoding="utf-8"))["state"], "REVOKED"
            )
            self.assertEqual(
                script["_revoke"](root, reference, scope, receipt_path)["state"], "REVOKED"
            )

    def test_dpapi_revocation_rejects_scope_mismatch_without_deleting(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        scope = _campaign_scope()
        reference = SecretReference(reference="dpapi://C16B_JIRA_TOKEN")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / ".local" / "secure-secrets" / "dpapi" / "C16B_JIRA_TOKEN.json"
            destination.parent.mkdir(parents=True)
            mismatched_scope = {**scope, "fence_token": "CFENCE-C16B-OTHER"}
            destination.write_text(
                json.dumps({"reference": reference.reference, "scope": mismatched_scope}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "scope does not match"):
                script["_revoke"](
                    root, reference, scope, root / ".local" / "evidence" / "revocation.json"
                )
            self.assertTrue(destination.exists())

    def test_dpapi_revocation_rejects_a_symlinked_receipt_parent(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "outside"
            target.mkdir()
            linked = root / ".local" / "evidence"
            linked.parent.mkdir()
            try:
                linked.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("local symlink creation is unavailable")
            with self.assertRaisesRegex(RuntimeError, "must not traverse a symlink"):
                script["_receipt_path"](
                    root,
                    linked / "revocation.json",
                    root / ".local" / "secure-secrets" / "dpapi" / "secret.json",
                )

    @unittest.skipUnless(os.name == "nt", "Windows ACL enforcement")
    def test_dpapi_envelope_acl_is_bound_to_the_scheduled_sid_and_verified(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "envelope.json"
            with patch.object(
                script["subprocess"],
                "run",
                side_effect=[
                    subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                    subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                    subprocess.CompletedProcess(["icacls.exe"], 0, "*S-1-5-21-1000:(M)\n", ""),
                    subprocess.CompletedProcess(
                        ["whoami.exe"], 0, '"COMFY-V4-CPU-01\\Windows 11","S-1-5-21-1000"\n', ""
                    ),
                ],
            ) as run:
                script["_write_dpapi_envelope"](
                    destination,
                    {"ciphertext_base64": "ciphertext-only"},
                    scheduled_principal_sid="S-1-5-21-1000",
                )
        self.assertEqual(run.call_count, 4)
        self.assertIn("*S-1-5-21-1000:(M)", run.call_args_list[0].args[0])
        self.assertEqual(run.call_args_list[1].args[0][-1], "/verify")
        self.assertEqual(run.call_args_list[2].args[0], ["icacls.exe", str(destination)])
        self.assertEqual(
            run.call_args_list[3].args[0], ["whoami.exe", "/user", "/fo", "csv", "/nh"]
        )

    @unittest.skipUnless(os.name == "nt", "Windows ACL enforcement")
    def test_dpapi_envelope_acl_readback_accepts_the_resolved_scheduled_trustee(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "envelope.json"
            with patch.object(
                script["subprocess"],
                "run",
                side_effect=[
                    subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                    subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                    subprocess.CompletedProcess(
                        ["icacls.exe"], 0, "COMFY-V4-CPU-01\\Windows 11:(M)\n", ""
                    ),
                    subprocess.CompletedProcess(
                        ["whoami.exe"], 0, '"COMFY-V4-CPU-01\\Windows 11","S-1-5-21-1000"\n', ""
                    ),
                ],
            ) as run:
                script["_write_dpapi_envelope"](
                    destination,
                    {"ciphertext_base64": "ciphertext-only"},
                    scheduled_principal_sid="S-1-5-21-1000",
                )
            self.assertTrue(destination.exists())
            self.assertEqual(run.call_count, 4)

    @unittest.skipUnless(os.name == "nt", "Windows ACL enforcement")
    def test_dpapi_envelope_acl_readback_rejects_an_unexpected_named_trustee(self) -> None:
        script = runpy.run_path(str(ROOT / "scripts" / "provision_dpapi_campaign_secret.py"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "envelope.json"
            with (
                patch.object(
                    script["subprocess"],
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                        subprocess.CompletedProcess(["icacls.exe"], 0, "", ""),
                        subprocess.CompletedProcess(
                            ["icacls.exe"],
                            0,
                            "*S-1-5-21-1000:(M)\nBUILTIN\\Administrators:(F)\n",
                            "",
                        ),
                    ],
                ),
                self.assertRaisesRegex(RuntimeError, "effective-access readback"),
            ):
                script["_write_dpapi_envelope"](
                    destination,
                    {"ciphertext_base64": "ciphertext-only"},
                    scheduled_principal_sid="S-1-5-21-1000",
                )
            self.assertFalse(destination.exists())

    def test_dpapi_envelope_persists_only_ciphertext_and_scope(self) -> None:
        scope = _campaign_scope(scheduler_lease_id="CLEASE-EXAMPLE")
        with patch(
            "project_pipeline.configuration.secrets.protect_dpapi_secret",
            return_value=b"ciphertext",
        ):
            envelope = build_dpapi_secret_envelope(
                "plaintext-never-persisted",
                reference=SecretReference(reference="dpapi://C16B_JIRA_TOKEN"),
                scope=scope,
            )
        self.assertEqual(envelope["reference"], "dpapi://C16B_JIRA_TOKEN")
        self.assertTrue(envelope["plaintext_persisted"] is False)
        self.assertNotIn("plaintext-never-persisted", json.dumps(envelope))

    def test_dpapi_resolver_rejects_a_mismatched_bound_scope(self) -> None:
        scope = _campaign_scope(scheduler_lease_id="CLEASE-C16B-ONE")
        reference = SecretReference(reference="dpapi://C16B_JIRA_TOKEN")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "project_pipeline.configuration.secrets.protect_dpapi_secret",
                return_value=b"ciphertext",
            ),
        ):
            root = Path(directory)
            destination = root / ".local" / "secure-secrets" / "dpapi"
            destination.mkdir(parents=True)
            (destination / "C16B_JIRA_TOKEN.json").write_text(
                json.dumps(build_dpapi_secret_envelope("test", reference=reference, scope=scope)),
                encoding="utf-8",
            )
            required_scope = {**scope, "fence_token": "CFENCE-C16B-TWO"}
            with self.assertRaises(SecretResolutionError):
                SecretResolver(root, required_scope=required_scope).resolve(reference)

    def test_dpapi_resolution_requires_a_fresh_bound_access_lease(self) -> None:
        reference = SecretReference(reference="dpapi://C16B_JIRA_TOKEN")
        scope = _campaign_scope(machine_id="test-machine", identity_id="S-1-5-21-4242")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "project_pipeline.configuration.secrets.protect_dpapi_secret",
                return_value=b"ciphertext",
            ),
            patch(
                "project_pipeline.configuration.secrets._dpapi_unprotect", return_value=b"resolved"
            ),
            patch(
                "project_pipeline.configuration.secrets.current_windows_principal_sid",
                return_value="S-1-5-21-4242",
            ),
            patch(
                "project_pipeline.configuration.secrets.socket.gethostname",
                return_value="test-machine",
            ),
        ):
            root = Path(directory)
            _write_security_policy(root)
            destination = root / ".local" / "secure-secrets" / "dpapi"
            destination.mkdir(parents=True)
            # This fixture deliberately contains only sealed test bytes.  The
            # plaintext path is covered by the envelope-builder test above;
            # this test exercises the resolver's access-lease boundary.
            sealed_fixture = {
                "schema_version": "2.0.0",
                "kind": "windows_current_user_credential_envelope",
                "reference": reference.reference,
                "scope": scope,
                "ciphertext_base64": "Y2lwaGVydGV4dA==",
                "plaintext_persisted": False,
            }
            (destination / "C16B_JIRA_TOKEN.json").write_text(
                json.dumps(sealed_fixture), encoding="utf-8"
            )
            with self.assertRaisesRegex(SecretResolutionError, "short-lived access lease"):
                SecretResolver(root, required_scope=scope).resolve(reference)
            stale_fence = issue_campaign_secret_access_lease(
                root,
                {**scope, "fence_token": "CFENCE-C16B-STALE"},
                access_identity="test-stale-fence",
            )
            with self.assertRaisesRegex(SecretResolutionError, "scope does not match"):
                SecretResolver(root, required_scope=scope, access_lease=stale_fence).resolve(
                    reference
                )
            access_lease = issue_campaign_secret_access_lease(
                root, scope, access_identity="test-current-fence"
            )
            resolver = SecretResolver(root, required_scope=scope, access_lease=access_lease)
            self.assertEqual(resolver.resolve(reference), "resolved")
            self.assertEqual(
                resolver.last_access_receipt["kind"], "campaign_secret_materialization_access"
            )
            self.assertNotIn("resolved", json.dumps(resolver.last_access_receipt))
            access_lease.revoke()
            with self.assertRaisesRegex(SecretResolutionError, "revoked"):
                resolver.resolve(reference)

    def test_campaign_secret_access_lease_never_exceeds_security_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_security_policy(root, maximum_seconds=900)
            scope = _campaign_scope()
            lease = issue_campaign_secret_access_lease(
                root, scope, access_identity="test-policy", ttl_seconds=900
            )
            self.assertLessEqual((lease.expires_at_utc - lease.issued_at_utc).total_seconds(), 900)
            with self.assertRaisesRegex(SecretResolutionError, "exceeds security policy"):
                issue_campaign_secret_access_lease(
                    root, scope, access_identity="test-policy-too-long", ttl_seconds=901
                )
            expired_issued_at = datetime.now(UTC) - timedelta(seconds=901)
            expired = CampaignSecretAccessLease(
                access_id="SACCESS-EXPIRED",
                access_identity="test-expired",
                issued_at_utc=expired_issued_at,
                expires_at_utc=expired_issued_at + timedelta(seconds=899),
                scope=scope,
            )
            with self.assertRaisesRegex(SecretResolutionError, "expired"):
                expired.validate(root, required_scope=scope)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI integration")
    def test_dpapi_current_user_round_trip(self) -> None:
        scope = _campaign_scope(
            machine_id=socket.gethostname(),
            identity_id=current_windows_principal_sid(),
            scheduler_lease_id="CLEASE-C16B-ROUNDTRIP",
            expires_at_utc=(datetime.now(UTC) + timedelta(days=6)).isoformat(),
        )
        reference = SecretReference(reference="dpapi://roundtrip")
        ciphertext = protect_dpapi_secret(
            "nonpersistent-test-material", reference=reference.reference, scope=scope
        )
        self.assertEqual(
            _dpapi_unprotect(
                ciphertext,
                json.dumps(
                    {"reference": reference.reference, "scope": scope},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            ).decode("utf-8"),
            "nonpersistent-test-material",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_security_policy(root)
            destination = root / ".local" / "secure-secrets" / "dpapi"
            destination.mkdir(parents=True)
            (destination / "roundtrip.json").write_text(
                json.dumps(
                    build_dpapi_secret_envelope(
                        "nonpersistent-test-material", reference=reference, scope=scope
                    )
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                SecretResolver(
                    root,
                    required_scope=scope,
                    access_lease=issue_campaign_secret_access_lease(
                        root, scope, access_identity="test-roundtrip"
                    ),
                ).resolve(reference),
                "nonpersistent-test-material",
            )
            with self.assertRaises(SecretResolutionError):
                SecretResolver(
                    root,
                    required_scope={**scope, "fence_token": "CFENCE-C16B-OTHER"},
                    access_lease=issue_campaign_secret_access_lease(
                        root, scope, access_identity="test-roundtrip-stale-fence"
                    ),
                ).resolve(reference)

    def test_secret_reference_syntax_is_strict(self) -> None:
        for value in ("plaintext", "vault://item", "file:///absolute", "env://BAD-NAME"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SecretReference(reference=value)

    def test_local_persistence_defaults_to_repository_confined_sqlite(self) -> None:
        configuration = load_runtime_configuration(ROOT, profile="local", environment={})
        self.assertEqual(configuration.settings.persistence.backend, "SQLITE_LOCAL")
        self.assertEqual(
            configuration.settings.database_path(ROOT),
            (ROOT / ".local" / "state" / "project_pipeline.db").resolve(),
        )

    def test_postgresql_profile_requires_secret_reference_and_keeps_it_redacted(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_runtime_configuration(
                ROOT,
                profile="local",
                environment={
                    "PROJECT_PIPELINE_PERSISTENCE_BACKEND": "POSTGRESQL",
                },
            )
        configuration = load_runtime_configuration(
            ROOT,
            profile="local",
            environment={
                "PROJECT_PIPELINE_PERSISTENCE_BACKEND": "POSTGRESQL",
                "PROJECT_PIPELINE_POSTGRESQL_DSN_REF": "env://PROJECT_PIPELINE_DATABASE_DSN",
            },
        )
        self.assertEqual(
            configuration.redacted_dict()["persistence"]["postgresql_dsn"],
            "env://PROJECT_PIPELINE_DATABASE_DSN",
        )

    def test_committed_runtime_profiles_and_schema_are_current(self) -> None:
        self.assertEqual(validate_runtime_configuration_files(ROOT), [])

    def test_generated_path_defaults_are_platform_neutral(self) -> None:
        schema = runtime_configuration_schema()
        for definition in ("RuntimePaths", "PersistenceSettings"):
            properties = schema["$defs"][definition]["properties"]
            path_defaults = [
                item["default"]
                for item in properties.values()
                if item.get("format") == "path" and "default" in item
            ]
            self.assertTrue(path_defaults)
            self.assertTrue(all("\\" not in value for value in path_defaults))
