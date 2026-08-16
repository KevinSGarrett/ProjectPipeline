from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

MANIFEST_PATH = Path("instructions/INSTRUCTION_MANIFEST.json")
COVERAGE_PATH = Path("instructions/INSTRUCTION_COVERAGE_MATRIX.json")
AUTHORITY_PATH = Path("instructions/AUTHORITY_MAP.json")
SCENARIOS_PATH = Path("instructions/policies/VALIDATION_SCENARIOS.json")
PPQS_PATH = Path("instructions/policies/PPQS_BENCHMARK_REGISTRY.json")
BRANCH_POLICY_PATH = Path("instructions/policies/BRANCH_PR_POLICY.json")
MUTATION_POLICY_PATH = Path("instructions/policies/EXTERNAL_MUTATION_AUTHORITY.json")
CONTEXT_ROUTING_PATH = Path("instructions/policies/CONTEXT_ROUTING.json")
SECURITY_POLICY_PATH = Path("config/security_policy.json")
JIRA_SYNC_POLICY_PATH = Path("config/jira/sync_policy.json")
REPOSITORY_POLICY_PATH = Path("config/repository_policy.json")
ENTRY_POINT = Path("AGENTS.md")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
INSTRUCTION_ID = re.compile(r"\|\s*Instruction ID\s*\|\s*`([^`]+)`\s*\|")
USES_ACTION = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MANDATORY_BOOTSTRAP = [
    "AGENTS.md",
    "instructions/README.md",
    "instructions/00_START_HERE.md",
    "instructions/01_AUTHORITY_AND_SOURCE_OF_TRUTH.md",
    "instructions/02_AUTONOMOUS_OPERATING_CONTRACT.md",
    "instructions/03_SESSION_BOOTSTRAP_AND_PREFLIGHT.md",
    "instructions/INSTRUCTION_MANIFEST.json",
    "instructions/INSTRUCTION_COVERAGE_MATRIX.json",
    "instructions/AUTHORITY_MAP.json",
    "instructions/SECOND_PASS_REQUIRED.md",
]


@dataclass(slots=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None


@dataclass(slots=True)
class Report:
    root: str
    checks: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        path: Path | str | None = None,
        line: int | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                message=message,
                path=str(path).replace("\\", "/") if path is not None else None,
                line=line,
            )
        )

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "ERROR"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "WARNING"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "root": self.root,
            "ok": self.ok,
            "checks": self.checks,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [asdict(item) for item in self.findings],
        }

    def render(self) -> str:
        lines = [
            f"Instruction validation: {'PASS' if self.ok else 'FAIL'}",
            f"Checks: {len(self.checks)} | Errors: {len(self.errors)} | Warnings: {len(self.warnings)}",
        ]
        for item in self.findings:
            location = ""
            if item.path:
                location = f" [{item.path}{':' + str(item.line) if item.line else ''}]"
            lines.append(f"{item.severity} {item.code}{location}: {item.message}")
        return "\n".join(lines)


def read_json(path: Path, report: Report, code: str) -> Any:
    if not path.exists():
        report.add("ERROR", code, "Required JSON file is missing", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report.add("ERROR", code, f"JSON is unreadable or invalid: {error}", path)
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_id(path: str, text: str | None = None) -> str:
    if path == "AGENTS.md":
        return "PP-ENTRY-ROOT"
    if text:
        match = INSTRUCTION_ID.search(text)
        if match:
            return match.group(1)
    slug = re.sub(r"[^A-Z0-9]+", "-", path.upper()).strip("-")
    return f"PP-ASSET-{slug}"


def instruction_files(root: Path, manifest: dict[str, Any]) -> list[Path]:
    files = [
        path
        for path in sorted((root / "instructions").rglob("*"))
        if path.is_file() and path.relative_to(root) != MANIFEST_PATH
    ]
    files.extend(sorted((root / ".agents" / "skills").glob("*/SKILL.md")))
    for relative in manifest.get("managed_support_paths", []):
        if isinstance(relative, str):
            files.append(root / relative)
    unique = {path.resolve(): path for path in files if path.is_file()}
    return [unique[key] for key in sorted(unique, key=lambda item: item.as_posix().lower())]


def build_hash_updated_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(json.dumps(manifest))
    paths = instruction_files(root, manifest)
    records: list[dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = None
        records.append(
            {
                "instruction_id": normalized_id(relative, text),
                "path": relative,
                "kind": _kind_for(relative),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    candidate["files"] = records
    return candidate


def write_manifest_atomically(root: Path, manifest: dict[str, Any]) -> None:
    target = root / MANIFEST_PATH
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            temporary_path = Path(stream.name)
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def commit_hash_update(root: Path, manifest: dict[str, Any], report: Report) -> bool:
    if not report.ok:
        report.add(
            "ERROR",
            "IMAN018",
            "Manifest hashes were not updated because semantic validation failed",
            MANIFEST_PATH,
        )
        return False
    try:
        write_manifest_atomically(root, manifest)
    except OSError as error:
        report.add(
            "ERROR", "IMAN017", f"Atomic manifest replacement failed: {error}", MANIFEST_PATH
        )
        return False
    report.checks.append("manifest_hash_update")
    return True


def _kind_for(relative: str) -> str:
    if relative == "AGENTS.md":
        return "ENTRY_POINT"
    if relative.startswith("instructions/policies/"):
        return "MACHINE_POLICY"
    if relative.startswith("instructions/schemas/"):
        return "SCHEMA"
    if relative.startswith("instructions/templates/"):
        return "TEMPLATE"
    if relative.startswith("instructions/examples/"):
        return "EXAMPLE"
    if relative.startswith("instructions/"):
        return "INSTRUCTION"
    if relative.startswith(".agents/skills/"):
        return "SKILL"
    if relative.startswith("scripts/"):
        return "VALIDATION_TOOL"
    if relative.startswith("tests/"):
        return "TEST"
    if relative.startswith(".github/"):
        return "GITHUB_GOVERNANCE"
    if relative.startswith("config/"):
        return "CONFIGURATION"
    if relative.startswith("src/"):
        return "IMPLEMENTATION_SUPPORT"
    return "INTEGRATION_SUPPORT"


def check_manifest(root: Path, report: Report, manifest: dict[str, Any]) -> None:
    report.checks.append("manifest")
    expected_identity = {
        "schema_version": "1.0.0",
        "instruction_pack_version": "1.0.0",
        "project_id": "PROJECT-PIPELINE",
        "project_name": "ProjectPipeline",
        "repository_url": "https://github.com/KevinSGarrett/ProjectPipeline",
        "canonical_local_root": "C:\\Project_X",
        "entry_point": "AGENTS.md",
        "instruction_root": "instructions",
    }
    for key, value in expected_identity.items():
        if manifest.get(key) != value:
            report.add("ERROR", "IMAN001", f"Manifest {key} must be {value!r}", MANIFEST_PATH)

    required_managed_paths = {
        ".gitignore",
        "config/jira/sync_policy.json",
        "config/security_policy.json",
    }
    managed_paths = set(manifest.get("managed_support_paths", []))
    for relative in sorted(required_managed_paths - managed_paths):
        report.add(
            "ERROR",
            "IMAN016",
            "Security-relevant support path is not hash-managed",
            relative,
        )

    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        report.add("ERROR", "IMAN002", "Manifest file records are missing", MANIFEST_PATH)
        return
    ids: set[str] = set()
    paths: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            report.add("ERROR", "IMAN003", "Manifest record is not an object", MANIFEST_PATH)
            continue
        instruction_id = record.get("instruction_id")
        relative = record.get("path")
        if not isinstance(instruction_id, str) or not instruction_id:
            report.add("ERROR", "IMAN004", "Manifest record has no instruction ID", MANIFEST_PATH)
            continue
        if instruction_id in ids:
            report.add(
                "ERROR", "IMAN005", f"Duplicate instruction ID: {instruction_id}", MANIFEST_PATH
            )
        ids.add(instruction_id)
        if not isinstance(relative, str) or not relative:
            report.add(
                "ERROR", "IMAN006", f"Manifest record {instruction_id} has no path", MANIFEST_PATH
            )
            continue
        if relative in paths:
            report.add("ERROR", "IMAN007", f"Duplicate manifest path: {relative}", MANIFEST_PATH)
        paths.add(relative)
        target = root / relative
        if not target.is_file():
            report.add("ERROR", "IMAN008", "Managed file is missing", relative)
            continue
        observed_hash = sha256_file(target)
        if record.get("sha256") != observed_hash:
            report.add("ERROR", "IMAN009", "Managed file hash differs from manifest", relative)
        if record.get("size_bytes") != target.stat().st_size:
            report.add("ERROR", "IMAN010", "Managed file size differs from manifest", relative)

    expected_paths = {
        path.relative_to(root).as_posix() for path in instruction_files(root, manifest)
    }
    for missing in sorted(expected_paths - paths):
        report.add("ERROR", "IMAN011", "Managed instruction asset is absent from manifest", missing)
    for extra in sorted(paths - expected_paths):
        report.add("ERROR", "IMAN012", "Manifest references an unmanaged or missing asset", extra)

    commands = manifest.get("commands", [])
    if not isinstance(commands, list) or not commands:
        report.add("ERROR", "IMAN013", "Canonical command contracts are missing", MANIFEST_PATH)
    else:
        for command in commands:
            if not isinstance(command, dict) or not command.get("command"):
                report.add("ERROR", "IMAN014", "Malformed command contract", MANIFEST_PATH)
                continue
            for relative in command.get("requires_paths", []):
                if not (root / relative).exists():
                    report.add(
                        "ERROR",
                        "IMAN015",
                        f"Command requires a missing path: {relative}",
                        MANIFEST_PATH,
                    )


def check_instruction_ids(root: Path, report: Report) -> None:
    report.checks.append("instruction_ids")
    observed: dict[str, str] = {}
    numbered = sorted((root / "instructions").glob("[0-9][0-9]_*.md"))
    expected = {f"PP-INST-{number:02d}" for number in range(21)}
    for path in numbered:
        text = path.read_text(encoding="utf-8")
        match = INSTRUCTION_ID.search(text)
        relative = path.relative_to(root).as_posix()
        if not match:
            report.add("ERROR", "IID001", "Instruction metadata has no ID", relative)
            continue
        instruction_id = match.group(1)
        if instruction_id in observed:
            report.add(
                "ERROR",
                "IID002",
                f"Duplicate instruction ID also used by {observed[instruction_id]}",
                relative,
            )
        observed[instruction_id] = relative
    missing = expected - set(observed)
    extra = set(observed) - expected
    for item in sorted(missing):
        report.add(
            "ERROR", "IID003", f"Required numbered instruction is missing: {item}", "instructions"
        )
    for item in sorted(extra):
        report.add("ERROR", "IID004", f"Unexpected numbered instruction ID: {item}", observed[item])


def check_coverage(root: Path, report: Report, coverage: dict[str, Any]) -> None:
    report.checks.append("coverage_matrix")
    domains = coverage.get("domains")
    if not isinstance(domains, list) or len(domains) < 20:
        report.add("ERROR", "COV001", "Coverage matrix has insufficient domains", COVERAGE_PATH)
        return
    seen: set[str] = set()
    for item in domains:
        if not isinstance(item, dict):
            report.add("ERROR", "COV002", "Coverage row is not an object", COVERAGE_PATH)
            continue
        domain = item.get("domain")
        primary = item.get("primary")
        if not isinstance(domain, str) or not domain:
            report.add("ERROR", "COV003", "Coverage row has no domain", COVERAGE_PATH)
            continue
        if domain in seen:
            report.add(
                "ERROR", "COV004", f"Domain has multiple primary rows: {domain}", COVERAGE_PATH
            )
        seen.add(domain)
        if not isinstance(primary, str) or not (root / primary).is_file():
            report.add(
                "ERROR",
                "COV005",
                f"Primary instruction is missing for {domain}: {primary}",
                COVERAGE_PATH,
            )
        supporting = item.get("supporting")
        if not isinstance(supporting, list):
            report.add(
                "ERROR",
                "COV006",
                f"Supporting references are malformed for {domain}",
                COVERAGE_PATH,
            )
            continue
        for relative in supporting:
            if isinstance(relative, str) and not (root / relative).exists():
                report.add(
                    "ERROR",
                    "COV007",
                    f"Supporting reference is missing for {domain}: {relative}",
                    COVERAGE_PATH,
                )
    required = {
        "startup",
        "authority",
        "plans",
        "requirements",
        "jira",
        "git",
        "github",
        "branches",
        "worktrees",
        "pull_requests",
        "ci",
        "testing",
        "security",
        "secrets",
        "ppqs_benchmarks",
        "upstream_repositories",
        "parallel_execution",
        "remote_machines",
        "budgeting",
        "failure_recovery",
        "human_escalation",
        "release",
        "completion",
        "instruction_maintenance",
    }
    for domain in sorted(required - seen):
        report.add(
            "ERROR",
            "COV008",
            f"Required domain has no primary instruction: {domain}",
            COVERAGE_PATH,
        )


def check_authority(report: Report, authority: dict[str, Any]) -> None:
    report.checks.append("authority_map")
    for key in ("normative_order", "observational_order"):
        rows = authority.get(key)
        if not isinstance(rows, list) or not rows:
            report.add("ERROR", "AUTH001", f"Authority order is missing: {key}", AUTHORITY_PATH)
            continue
        ranks = [row.get("rank") for row in rows if isinstance(row, dict)]
        if ranks != list(range(1, len(ranks) + 1)):
            report.add(
                "ERROR", "AUTH002", f"Authority ranks are not contiguous in {key}", AUTHORITY_PATH
            )
        classes = [row.get("class") for row in rows if isinstance(row, dict)]
        if len(classes) != len(set(classes)):
            report.add(
                "ERROR", "AUTH003", f"Authority classes are duplicated in {key}", AUTHORITY_PATH
            )
    resolutions = authority.get("conflict_resolution")
    if not isinstance(resolutions, list) or len(resolutions) < 4:
        report.add(
            "ERROR", "AUTH004", "Conflict-resolution procedure is incomplete", AUTHORITY_PATH
        )


def check_json_schemas(root: Path, report: Report, documents: dict[Path, Any]) -> None:
    report.checks.append("json_schemas")
    try:
        import jsonschema
    except ImportError:
        report.add(
            "WARNING",
            "SCHEMA900",
            "jsonschema is unavailable; structural checks still ran",
            "instructions/schemas",
        )
        return
    pairs = [
        (MANIFEST_PATH, Path("instructions/schemas/instruction_manifest.schema.json")),
        (COVERAGE_PATH, Path("instructions/schemas/instruction_coverage_matrix.schema.json")),
        (AUTHORITY_PATH, Path("instructions/schemas/authority_map.schema.json")),
    ]
    for document_path, schema_path in pairs:
        document = documents.get(document_path)
        schema = documents.get(schema_path)
        if document is None or schema is None:
            continue
        try:
            jsonschema.Draft202012Validator(schema).validate(document)
        except jsonschema.ValidationError as error:
            report.add(
                "ERROR", "SCHEMA001", f"Schema validation failed: {error.message}", document_path
            )


def managed_text_files(root: Path, manifest: dict[str, Any]) -> Iterable[Path]:
    for path in instruction_files(root, manifest):
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        yield path


def check_links(root: Path, report: Report, manifest: dict[str, Any]) -> None:
    report.checks.append("markdown_links")
    for path in managed_text_files(root, manifest):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), 1):
            for match in MARKDOWN_LINK.finditer(line):
                raw = match.group(1).strip().split()[0].strip("<>")
                if raw.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target_text = unquote(raw.split("#", 1)[0])
                if not target_text:
                    continue
                target = (path.parent / target_text).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    report.add(
                        "ERROR", "LINK001", f"Link escapes repository: {raw}", relative, number
                    )
                    continue
                if not target.exists():
                    report.add("ERROR", "LINK002", f"Broken internal link: {raw}", relative, number)


def check_content_safety(root: Path, report: Report, manifest: dict[str, Any]) -> None:
    report.checks.append("content_safety")
    repository_policy = read_json(root / "config/repository_policy.json", report, "SAFE000") or {}
    parts = (
        repository_policy.get("forbidden_term_parts", [])
        if isinstance(repository_policy, dict)
        else []
    )
    token = (
        "".join(parts)
        if isinstance(parts, list) and all(isinstance(item, str) for item in parts)
        else "wa" + "ve"
    )
    suffix = (
        repository_policy.get("forbidden_term_plural_suffix", "s")
        if isinstance(repository_policy, dict)
        else "s"
    )
    prohibited = re.compile(
        r"\b" + re.escape(token) + re.escape(str(suffix)) + r"?\b", re.IGNORECASE
    )
    stale_patterns = [
        re.compile(r"C:\\" + "Project" + "_Pipeline"),
        re.compile(r"github\.com/KevinSGarrett/" + "Project" + "_Pipeline"),
        re.compile(r"(?<!s)/" + "instruction" + r"/"),
    ]
    secret_patterns = [
        re.compile("AK" + "IA" + r"[0-9A-Z]{16}"),
        re.compile("gh" + r"[pousr]_[A-Za-z0-9]{30,}"),
        re.compile("xox" + r"[abprs]-[A-Za-z0-9-]{20,}"),
        re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?" + "PRIVATE KEY"),
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\b"
            r"\s*[:=]\s*[\"'][^\"']{8,}[\"']"
        ),
    ]
    marker_patterns = [
        re.compile(r"\b" + "TO" + "DO" + r"\b"),
        re.compile(r"\b" + "FIX" + "ME" + r"\b"),
        re.compile("Not" + "Implemented" + "Error"),
        re.compile("assert" + " True"),
        re.compile(r"^\s*pass\s*(?:#.*)?$", re.MULTILINE),
    ]
    for path in managed_text_files(root, manifest):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if prohibited.search(relative) or prohibited.search(text):
            report.add(
                "ERROR",
                "SAFE001",
                "Repository-prohibited terminology appears in managed instructions",
                relative,
            )
        for pattern in stale_patterns:
            if pattern.search(text):
                report.add(
                    "ERROR",
                    "SAFE002",
                    "Obsolete repository identity or singular instruction path appears",
                    relative,
                )
        for pattern in secret_patterns:
            if pattern.search(text):
                report.add(
                    "ERROR", "SAFE003", "Possible secret appears in managed instructions", relative
                )
        for pattern in marker_patterns:
            if pattern.search(text):
                report.add(
                    "ERROR",
                    "SAFE004",
                    "Unresolved implementation marker appears in managed instructions",
                    relative,
                )


def check_entry_point(root: Path, report: Report) -> None:
    report.checks.append("entry_point")
    path = root / ENTRY_POINT
    if not path.is_file():
        report.add("ERROR", "ENTRY001", "Root AGENTS.md is missing", ENTRY_POINT)
        return
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > 220:
        report.add(
            "ERROR", "ENTRY002", f"Root AGENTS.md is too large: {len(lines)} lines", ENTRY_POINT
        )
    required_fragments = [
        "instructions/00_START_HERE.md",
        "AUTHORITY_AND_SOURCE_OF_TRUTH",
        "doctor --root .",
        "control sequence --root .",
        "PPQS",
        "Completion Gate",
        "Code review rules",
    ]
    for fragment in required_fragments:
        if fragment.lower() not in text.lower():
            report.add(
                "ERROR",
                "ENTRY003",
                f"Root entry point lacks required route: {fragment}",
                ENTRY_POINT,
            )


def check_policies(root: Path, report: Report, documents: dict[Path, Any]) -> None:
    report.checks.append("policy_consistency")
    branch = documents.get(BRANCH_POLICY_PATH)
    if isinstance(branch, dict):
        if (
            branch.get("default_branch") != "main"
            or branch.get("permanent_development_branch") is not False
        ):
            report.add(
                "ERROR",
                "POL001",
                "Branch topology conflicts with governing instruction",
                BRANCH_POLICY_PATH,
            )
        for pattern in branch.get("branch_patterns", []):
            try:
                re.compile(pattern)
            except re.error as error:
                report.add(
                    "ERROR", "POL002", f"Invalid branch pattern: {error}", BRANCH_POLICY_PATH
                )
    mutation = documents.get(MUTATION_POLICY_PATH)
    if isinstance(mutation, dict):
        categories = mutation.get("categories", {})
        required = {
            "AUTONOMOUSLY_AUTHORIZED_WITHIN_PROJECT_POLICY",
            "POLICY_GATED",
            "HUMAN_REQUIRED",
            "PROHIBITED",
        }
        if not isinstance(categories, dict) or set(categories) != required:
            report.add(
                "ERROR",
                "POL003",
                "External mutation categories are incomplete or unexpected",
                MUTATION_POLICY_PATH,
            )
        sequence = mutation.get("unknown_outcome_sequence", [])
        if (
            not isinstance(sequence, list)
            or len(sequence) < 4
            or sequence[0] != "STOP_WRITE_RETRIES"
        ):
            report.add(
                "ERROR", "POL004", "Unknown-outcome sequence is incomplete", MUTATION_POLICY_PATH
            )
    context_routing = documents.get(CONTEXT_ROUTING_PATH)
    if (
        not isinstance(context_routing, dict)
        or context_routing.get("default_bootstrap") != MANDATORY_BOOTSTRAP
    ):
        report.add(
            "ERROR",
            "POL005",
            "Context routing must retain the complete mandatory bootstrap set",
            CONTEXT_ROUTING_PATH,
        )
    security_policy = documents.get(SECURITY_POLICY_PATH)
    if not isinstance(security_policy, dict):
        security_policy = {}
    required_capabilities = {"MODIFY_INSTRUCTIONS", "MODIFY_POLICY", "COMPLETE_PROJECT"}
    high_impact = set(security_policy.get("high_impact_capabilities", []))
    self_modification = security_policy.get("self_modification", {})
    external_egress = security_policy.get("external_egress", {})
    if (
        security_policy.get("high_impact_requires_independent_approval") is not True
        or not required_capabilities.issubset(high_impact)
        or not isinstance(self_modification, dict)
        or self_modification.get("independent_review_for_control_plane") is not True
        or self_modification.get("rollback_material_required") is not True
        or self_modification.get("security_verification_required") is not True
        or not isinstance(external_egress, dict)
        or external_egress.get("secret") != "DENY"
        or external_egress.get("local_only") != "DENY"
    ):
        report.add(
            "ERROR",
            "POL006",
            "Security self-modification, independence, rollback, or egress invariants were weakened",
            SECURITY_POLICY_PATH,
        )
    jira_policy = documents.get(JIRA_SYNC_POLICY_PATH)
    if not isinstance(jira_policy, dict):
        jira_policy = {}
    if jira_policy.get("authority_mode") != "SOURCE_CONTROLLED_LOCAL":
        report.add(
            "ERROR",
            "POL007",
            "Jira authority mode must remain source-controlled local",
            JIRA_SYNC_POLICY_PATH,
        )
    if jira_policy.get("require_human_for_remote_done") is not True:
        report.add(
            "ERROR", "POL008", "Remote Done must retain human requirement", JIRA_SYNC_POLICY_PATH
        )
    repo_policy = documents.get(REPOSITORY_POLICY_PATH)
    if not isinstance(repo_policy, dict):
        repo_policy = {}
    content = repo_policy.get("content_validation", {}) if isinstance(repo_policy, dict) else {}
    exclusions = content.get("placeholder_excluded_roots", []) if isinstance(content, dict) else []
    if exclusions != ["dummy"]:
        report.add(
            "ERROR",
            "POL009",
            "Placeholder exclusion must be narrowly scoped to dummy",
            REPOSITORY_POLICY_PATH,
        )


def check_actions_pinned(root: Path, report: Report) -> None:
    report.checks.append("github_action_pinning")
    workflow_root = root / ".github" / "workflows"
    for path in sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for match in USES_ACTION.finditer(text):
            value = match.group(1)
            if value.startswith("./"):
                continue
            if "@" not in value:
                report.add(
                    "ERROR",
                    "ACT001",
                    f"Action has no immutable reference: {value}",
                    path.relative_to(root),
                )
                continue
            action, reference = value.rsplit("@", 1)
            if not action or not FULL_SHA.fullmatch(reference):
                report.add(
                    "ERROR",
                    "ACT002",
                    f"Action is not pinned to a full commit SHA: {value}",
                    path.relative_to(root),
                )


def check_ppqs(root: Path, report: Report, ppqs: dict[str, Any]) -> None:
    report.checks.append("ppqs_registry_and_boundaries")
    packs = ppqs.get("packs")
    if not isinstance(packs, list) or len(packs) != 8:
        report.add("ERROR", "PPQS001", "Exactly eight PPQS packs must be registered", PPQS_PATH)
        return
    ids: set[str] = set()
    for item in packs:
        if not isinstance(item, dict):
            report.add("ERROR", "PPQS002", "PPQS registry row is malformed", PPQS_PATH)
            continue
        benchmark_id = item.get("benchmark_id")
        relative = item.get("path")
        if not isinstance(benchmark_id, str) or benchmark_id in ids:
            report.add(
                "ERROR", "PPQS003", f"Duplicate or invalid benchmark ID: {benchmark_id}", PPQS_PATH
            )
        ids.add(str(benchmark_id))
        if not isinstance(relative, str):
            report.add("ERROR", "PPQS004", f"Pack path is invalid for {benchmark_id}", PPQS_PATH)
            continue
        pack = root / relative
        if not pack.is_dir():
            report.add(
                "ERROR", "PPQS005", f"Pack directory is missing for {benchmark_id}", relative
            )
            continue
        for required in item.get("required_files", []):
            if not (pack / required).is_file():
                report.add(
                    "ERROR", "PPQS006", f"Required pack file is missing: {required}", relative
                )
        pack_manifest = read_json(pack / "PACK_MANIFEST.json", report, "PPQS007") or {}
        if pack_manifest.get("benchmark_id") != benchmark_id:
            report.add(
                "ERROR", "PPQS008", "Pack manifest benchmark ID differs from registry", relative
            )
        boundary = read_json(pack / "constraints/benchmark_boundary.json", report, "PPQS009") or {}
        prohibited = boundary.get("candidate_must_not_read", [])
        if not isinstance(prohibited, list) or not any(
            "Oracle" in str(value) for value in prohibited
        ):
            report.add(
                "ERROR", "PPQS010", "Boundary does not explicitly prohibit Oracle access", relative
            )
        if (
            boundary.get("hard_gate_on_violation")
            != "ORACLE_ACCESS_ATTEMPT_OR_UNAUTHORIZED_EXTERNAL_MUTATION"
        ):
            report.add("ERROR", "PPQS011", "Boundary hard gate is missing or changed", relative)
    expected_ids = {f"PPQS-{number:02d}" for number in range(1, 9)}
    if ids != expected_ids:
        report.add(
            "ERROR", "PPQS012", f"PPQS IDs differ from expected set: {sorted(ids)}", PPQS_PATH
        )
    for path in (root / "dummy").rglob("*"):
        if path.name.lower() == "oracle_pack":
            report.add(
                "ERROR",
                "PPQS013",
                "Candidate-visible repository contains an Oracle directory",
                path.relative_to(root),
            )


def check_scenarios(report: Report, scenarios: dict[str, Any]) -> None:
    report.checks.append("scenario_coverage")
    rows = scenarios.get("scenarios")
    if not isinstance(rows, list):
        report.add("ERROR", "SCEN001", "Scenario registry is missing", SCENARIOS_PATH)
        return
    ids = {row.get("id") for row in rows if isinstance(row, dict)}
    expected = set("ABCDEFGHIJKL")
    if ids != expected:
        report.add(
            "ERROR",
            "SCEN002",
            f"Scenario IDs must be A through L; observed {sorted(ids)}",
            SCENARIOS_PATH,
        )
    for row in rows:
        if not isinstance(row, dict) or not row.get("trigger") or not row.get("expected"):
            report.add(
                "ERROR",
                "SCEN003",
                "Scenario row lacks trigger or expected behavior",
                SCENARIOS_PATH,
            )


def load_documents(root: Path, report: Report) -> dict[Path, Any]:
    paths = [
        MANIFEST_PATH,
        COVERAGE_PATH,
        AUTHORITY_PATH,
        SCENARIOS_PATH,
        PPQS_PATH,
        BRANCH_POLICY_PATH,
        MUTATION_POLICY_PATH,
        CONTEXT_ROUTING_PATH,
        SECURITY_POLICY_PATH,
        JIRA_SYNC_POLICY_PATH,
        REPOSITORY_POLICY_PATH,
        Path("instructions/schemas/instruction_manifest.schema.json"),
        Path("instructions/schemas/instruction_coverage_matrix.schema.json"),
        Path("instructions/schemas/authority_map.schema.json"),
    ]
    documents: dict[Path, Any] = {}
    for index, relative in enumerate(paths, 1):
        documents[relative] = read_json(root / relative, report, f"JSON{index:03d}")
    return documents


def validate_instruction_system(root: Path, *, update: bool = False) -> Report:
    root = root.resolve()
    report = Report(root=str(root))
    documents = load_documents(root, report)
    manifest = documents.get(MANIFEST_PATH)
    if not isinstance(manifest, dict):
        return report
    if update:
        manifest = build_hash_updated_manifest(root, manifest)
        documents[MANIFEST_PATH] = manifest
    coverage = documents.get(COVERAGE_PATH)
    authority = documents.get(AUTHORITY_PATH)
    scenarios = documents.get(SCENARIOS_PATH)
    ppqs = documents.get(PPQS_PATH)

    check_manifest(root, report, manifest)
    check_instruction_ids(root, report)
    if isinstance(coverage, dict):
        check_coverage(root, report, coverage)
    if isinstance(authority, dict):
        check_authority(report, authority)
    check_json_schemas(root, report, documents)
    check_links(root, report, manifest)
    check_content_safety(root, report, manifest)
    check_entry_point(root, report)
    check_policies(root, report, documents)
    check_actions_pinned(root, report)
    if isinstance(ppqs, dict):
        check_ppqs(root, report, ppqs)
    if isinstance(scenarios, dict):
        check_scenarios(report, scenarios)
    if update:
        commit_hash_update(root, manifest, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the ProjectPipeline instruction system")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--update-hashes", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = validate_instruction_system(args.root, update=args.update_hashes)
    print(report.render())
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
