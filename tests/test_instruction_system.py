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


def test_required_codeql_check_runs_for_every_pull_request() -> None:
    workflow = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    pull_request_block = workflow.split("  pull_request:\n", 1)[1].split("  push:\n", 1)[0]
    assert "branches: [main]" in pull_request_block
    assert "paths:" not in pull_request_block


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
        module.ASSURANCE_POLICY_PATH: json.loads(
            (ROOT / module.ASSURANCE_POLICY_PATH).read_text(encoding="utf-8")
        ),
    }
    weakened = copy.deepcopy(documents)
    weakened[module.CONTEXT_ROUTING_PATH]["default_bootstrap"] = ["AGENTS.md"]
    weakened[module.SECURITY_POLICY_PATH]["self_modification"]["rollback_material_required"] = False
    report = module.Report(root=str(ROOT))
    module.check_policies(ROOT, report, weakened)
    assert {item.code for item in report.errors}.issuperset({"POL005", "POL006"})


def test_remote_worker_instructions_do_not_assign_operator_work() -> None:
    remote = (ROOT / "instructions/16_REMOTE_MACHINE_AND_RESOURCE_PROTOCOL.md").read_text(
        encoding="utf-8"
    )
    skill = (ROOT / ".agents/skills/remote-cpu-worker/SKILL.md").read_text(encoding="utf-8")
    authority = json.loads((ROOT / "instructions/AUTHORITY_MAP.json").read_text(encoding="utf-8"))
    assert "exact operator action" not in remote
    assert "exact operator action" not in skill
    assert "actionable escalation" not in json.dumps(authority)
    assert "BLOCKED_EXTERNAL" in remote
    assert "no operator work assignment" in skill


def test_routine_development_policy_has_no_human_approval_terminal() -> None:
    mutation = json.loads(
        (ROOT / "instructions/policies/EXTERNAL_MUTATION_AUTHORITY.json").read_text(
            encoding="utf-8"
        )
    )
    categories = mutation["categories"]
    assert "HUMAN_REQUIRED" not in categories
    assert mutation["external_precondition_behavior"] == {
        "assign_operator_work": False,
        "continue_unaffected_work": True,
        "fabricate_capability": False,
        "schedule_autonomous_recheck": True,
        "state": "BLOCKED_EXTERNAL",
    }
    jira_policy = json.loads((ROOT / "config/jira/sync_policy.json").read_text(encoding="utf-8"))
    assert jira_policy["require_completion_evidence_for_remote_done"] is True
    assert jira_policy["remote_done_human_approval_required"] is False


def test_delivery_progress_policy_weakening_is_rejected() -> None:
    module = load_script(
        "validate_instructions_delivery_guard", ROOT / "scripts/validate_instructions.py"
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
        module.ASSURANCE_POLICY_PATH: json.loads(
            (ROOT / module.ASSURANCE_POLICY_PATH).read_text(encoding="utf-8")
        ),
    }
    weakened = copy.deepcopy(documents)
    weakened[module.BRANCH_POLICY_PATH]["delivery_progress_gate"]["lifecycle_only_pr_allowed"] = (
        True
    )
    weakened[module.ASSURANCE_POLICY_PATH]["delivery_progress"][
        "maximum_noncritical_administrative_ratio_milli"
    ] = 1000
    report = module.Report(root=str(ROOT))
    module.check_policies(ROOT, report, weakened)
    assert {item.code for item in report.errors}.issuperset({"POL010", "POL011"})


def test_quality_workflow_enforces_exact_head_delivery_progress() -> None:
    workflow = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    assert "assurance delivery-gate" in workflow
    assert "--base-ref" in workflow
    assert '--head-ref "${{ github.event.pull_request.head.sha }}"' in workflow
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow


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
