from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from project_pipeline.configuration import (
    ConfigurationError,
    SecretReference,
    SecretResolutionError,
    SecretResolver,
    load_runtime_configuration,
    validate_runtime_configuration_files,
)

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
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
