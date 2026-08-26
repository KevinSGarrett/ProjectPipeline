from __future__ import annotations

import importlib.util
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


def make_public_checkout(root: Path) -> None:
    (root / "README.md").write_text("# ProjectPipeline\n", encoding="utf-8")
    (root / "LICENSE").write_text("LicenseRef-Proprietary\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'project-pipeline'\n", encoding="utf-8")
    (root / "src/project_pipeline").mkdir(parents=True)
    (root / "scripts").mkdir()
    for name in ("validate_instructions.py", "instruction_cold_start.py"):
        (root / "scripts" / name).write_text(
            (ROOT / "scripts" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )


def test_public_checkout_does_not_require_private_maintainer_records() -> None:
    module = load_script("validate_public_checkout", ROOT / "scripts/validate_instructions.py")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_public_checkout(root)
        report = module.validate_instruction_system(root)

    assert report.errors == []
    assert report.checks == ["public_source_mode"]
    assert [item.code for item in report.findings] == ["PUBLIC001"]


def test_public_cold_start_routes_to_public_documentation() -> None:
    module = load_script("public_cold_start", ROOT / "scripts/instruction_cold_start.py")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_public_checkout(root)
        payload = module.build_cold_start(root)

    assert payload["ready"] is True
    assert payload["mode"] == "PUBLIC_SOURCE"
    assert payload["first_read"] == ["README.md", "CONTRIBUTING.md", "SECURITY.md"]
    assert payload["routing"] == {}
