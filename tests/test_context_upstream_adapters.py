import pytest

from project_pipeline.upstream_integrations.context import DoclingAdapter, MarkItDownAdapter


def test_markitdown_availability_is_truthful_boolean(tmp_path):
    a = MarkItDownAdapter()
    p = tmp_path / "a.txt"
    p.write_text("x")
    assert isinstance(a.available(), bool)


def test_docling_rejects_large_file_before_dependency(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"x" * 20)
    with pytest.raises(ValueError):
        DoclingAdapter(max_file_size=10).convert(p)


def test_docling_missing_file_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        DoclingAdapter().convert(tmp_path / "missing.pdf")


def test_markitdown_adapter_disables_plugins_and_returns_text(monkeypatch, tmp_path):
    import sys
    import types

    from project_pipeline.upstream_integrations.context import MarkItDownAdapter

    calls = {}

    class FakeResult:
        text_content = "normalized markdown"

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def convert(self, source):
            calls["source"] = source
            return FakeResult()

    module = types.ModuleType("markitdown")
    module.MarkItDown = FakeMarkItDown
    monkeypatch.setitem(sys.modules, "markitdown", module)
    source = tmp_path / "input.txt"
    source.write_text("hello", encoding="utf-8")
    assert MarkItDownAdapter().convert(source) == "normalized markdown"
    assert calls["kwargs"] == {"enable_plugins": False}
    assert calls["source"] == source.resolve()


def test_docling_adapter_passes_page_and_size_limits(monkeypatch, tmp_path):
    import sys
    import types

    from project_pipeline.upstream_integrations.context import DoclingAdapter

    calls = {}

    class FakeDocument:
        def export_to_markdown(self):
            return "# Structured"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, source, **kwargs):
            calls["source"] = source
            calls["kwargs"] = kwargs
            return FakeResult()

    package = types.ModuleType("docling")
    package.__path__ = []
    converter_module = types.ModuleType("docling.document_converter")
    converter_module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", package)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)
    source = tmp_path / "input.pdf"
    source.write_bytes(b"pdf")
    adapter = DoclingAdapter(max_file_size=1024, max_num_pages=7)
    assert adapter.convert(source) == "# Structured"
    assert calls["source"] == source.resolve()
    assert calls["kwargs"] == {"max_num_pages": 7, "max_file_size": 1024}
