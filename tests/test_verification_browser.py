from pathlib import Path

from project_pipeline.verification.browser import find_chromium, render_verification_report


def test_render_verification_report_is_local_and_semantic(project_root: Path):
    target = render_verification_report(project_root, summary={"tests": 1, "gaps": 0})
    text = target.read_text(encoding="utf-8")
    assert '<html lang="en">' in text
    assert "<main" in text
    assert "<h1>Pass 16 Verification Report</h1>" in text
    assert "http://" not in text and "https://" not in text


def test_find_chromium_returns_path_or_none():
    value = find_chromium(("/definitely/missing/chromium",))
    assert value is None or Path(value).is_file()


def test_find_chromium_prefers_an_explicit_existing_binary(tmp_path: Path) -> None:
    binary = tmp_path / "chrome.exe"
    binary.write_bytes(b"mz")
    assert find_chromium((str(binary),)) == str(binary)
