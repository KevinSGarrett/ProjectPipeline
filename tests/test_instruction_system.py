from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_instruction_validator_has_no_errors() -> None:
    module = load_script("validate_instructions", ROOT / "scripts/validate_instructions.py")
    report = module.validate_instruction_system(ROOT)
    assert report.errors == [], report.render()


def test_cold_start_is_complete_and_chat_independent() -> None:
    module = load_script("instruction_cold_start", ROOT / "scripts/instruction_cold_start.py")
    payload = module.build_cold_start(ROOT)
    assert payload["ready"] is True
    assert payload["missing"] == []
    assert payload["first_read"][0] == "AGENTS.md"
    assert "completion" in payload["routing"]
    assert payload["scenario_ids"] == list("ABCDEFGHIJKL")


def test_coverage_has_one_primary_per_domain() -> None:
    payload = json.loads(
        (ROOT / "instructions/INSTRUCTION_COVERAGE_MATRIX.json").read_text(encoding="utf-8")
    )
    domains = payload["domains"]
    names = [item["domain"] for item in domains]
    assert len(names) == len(set(names))
    for item in domains:
        assert (ROOT / item["primary"]).is_file()


def test_ppqs_registry_has_eight_immutable_seed_packs() -> None:
    payload = json.loads(
        (ROOT / "instructions/policies/PPQS_BENCHMARK_REGISTRY.json").read_text(encoding="utf-8")
    )
    assert payload["canonical_seed_policy"] == "IMMUTABLE"
    assert payload["oracle_policy"] == "PROHIBITED"
    assert [item["benchmark_id"] for item in payload["packs"]] == [
        f"PPQS-{number:02d}" for number in range(1, 9)
    ]
    for item in payload["packs"]:
        assert (ROOT / item["path"] / "constraints/benchmark_boundary.json").is_file()


def test_missing_root_entry_point_is_rejected() -> None:
    module = load_script(
        "validate_instructions_missing_entry", ROOT / "scripts/validate_instructions.py"
    )
    with tempfile.TemporaryDirectory() as directory:
        report = module.Report(root=directory)
        module.check_entry_point(Path(directory), report)
    assert any(item.code == "ENTRY001" for item in report.errors)


def test_mutable_action_reference_is_rejected() -> None:
    module = load_script(
        "validate_instructions_action_pin", ROOT / "scripts/validate_instructions.py"
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workflow = root / ".github" / "workflows" / "quality.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
        report = module.Report(root=directory)
        module.check_actions_pinned(root, report)
    assert any(item.code == "ACT002" for item in report.errors)


def test_context_and_security_policy_weakening_are_rejected() -> None:
    module = load_script(
        "validate_instructions_policy_guard", ROOT / "scripts/validate_instructions.py"
    )
    documents = {
        module.BRANCH_POLICY_PATH: json.loads(
            (ROOT / module.BRANCH_POLICY_PATH).read_text(encoding="utf-8")
        ),
        module.MUTATION_POLICY_PATH: json.loads(
            (ROOT / module.MUTATION_POLICY_PATH).read_text(encoding="utf-8")
        ),
        module.CONTEXT_ROUTING_PATH: json.loads(
            (ROOT / module.CONTEXT_ROUTING_PATH).read_text(encoding="utf-8")
        ),
        module.SECURITY_POLICY_PATH: json.loads(
            (ROOT / module.SECURITY_POLICY_PATH).read_text(encoding="utf-8")
        ),
        module.JIRA_SYNC_POLICY_PATH: json.loads(
            (ROOT / module.JIRA_SYNC_POLICY_PATH).read_text(encoding="utf-8")
        ),
        module.REPOSITORY_POLICY_PATH: json.loads(
            (ROOT / module.REPOSITORY_POLICY_PATH).read_text(encoding="utf-8")
        ),
    }
    weakened = copy.deepcopy(documents)
    weakened[module.CONTEXT_ROUTING_PATH]["default_bootstrap"] = ["AGENTS.md"]
    weakened[module.SECURITY_POLICY_PATH]["self_modification"]["rollback_material_required"] = False
    report = module.Report(root=str(ROOT))
    module.check_policies(ROOT, report, weakened)
    assert {item.code for item in report.errors}.issuperset({"POL005", "POL006"})


def test_failed_validation_does_not_replace_manifest() -> None:
    module = load_script(
        "validate_instructions_atomic_update", ROOT / "scripts/validate_instructions.py"
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / module.MANIFEST_PATH
        target.parent.mkdir(parents=True)
        target.write_text('{"state":"original"}\n', encoding="utf-8")
        report = module.Report(root=directory)
        report.add("ERROR", "TEST", "semantic failure")
        committed = module.commit_hash_update(root, {"state": "candidate"}, report)
        assert committed is False
        assert json.loads(target.read_text(encoding="utf-8")) == {"state": "original"}
