from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from project_pipeline.cli import _secret_resolver
from project_pipeline.configuration import (
    ConfigurationError,
    SecretReference,
    SecretResolutionError,
    SecretResolver,
    load_runtime_configuration,
    runtime_configuration_schema,
    validate_runtime_configuration_files,
)
from project_pipeline.configuration.campaign_environment import (
    limited_campaign_subprocess_environment,
    load_campaign_runtime_environment,
)
from project_pipeline.configuration.secrets import build_dpapi_secret_envelope

ROOT = Path(__file__).resolve().parents[1]


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
                "JIRA_BASE_URL=https://example.atlassian.net\n"
                "JIRA_USER_EMAIL=worker@example.test\n"
                "JIRA_API_TOKEN_REF=dpapi://C16B_JIRA_TOKEN\n"
                "GITHUB_TOKEN_REF=gh-auth://default\n",
                encoding="utf-8",
            )
            values = load_campaign_runtime_environment(ROOT, env_file)
            environment = limited_campaign_subprocess_environment(
                ROOT,
                env_file,
                source={"PATH": "safe-path", "SYSTEMROOT": "safe-root", "UNRELATED_SECRET": "no"},
            )
        self.assertEqual(values["JIRA_API_TOKEN_REF"], "dpapi://C16B_JIRA_TOKEN")
        self.assertEqual(environment["GITHUB_TOKEN_REF"], "gh-auth://default")
        self.assertNotIn("UNRELATED_SECRET", environment)

    def test_dpapi_envelope_persists_only_ciphertext_and_scope(self) -> None:
        scope = {
            "project_id": "PROJECT-PIPELINE",
            "cycle_id": "CYCLE-16-B",
            "machine_id": "COMFY-V4-CPU-01",
            "identity_id": "Windows 11",
            "lease_id": "SLEASE-EXAMPLE",
            "expires_at_utc": "2099-01-01T00:00:00+00:00",
        }
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
