import ast
from pathlib import Path

import docstring_parser


def test_iris_llm_tool_docstrings_declare_runtime_parameter_types() -> None:
    """Ensure AstrBot's decorator can build schemas for the Iris read tools."""

    source = (
        Path(__file__).resolve().parents[2]
        / "data/plugins/astrbot_plugin_iris_memory/main.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    expected = {
        "iris_memory_facts_tool",
        "iris_memory_graph_tool",
        "iris_memory_review_candidates_tool",
        "iris_memory_feedback_tool",
    }
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in expected:
            continue
        found.add(node.name)
        parsed = docstring_parser.parse(ast.get_docstring(node) or "")
        assert parsed.params
        assert all(param.type_name for param in parsed.params)
    assert found == expected


def test_iris_memory_uses_configured_persona_scope() -> None:
    """Ensure memory capture and retrieval use the ConfigStore scope helpers."""

    root = Path(__file__).resolve().parents[2]
    sources = [
        root / "data/plugins/astrbot_plugin_iris_memory/main.py",
        root
        / "data/plugins/astrbot_plugin_iris_memory/iris_memory/processing/message_processor.py",
        root
        / "data/plugins/astrbot_plugin_iris_memory/iris_memory/commands/handlers.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert 'cfg.get("persona_isolation.default_persona_id"' not in text
    assert "get_persona_id_for_storage" in text
    assert "get_persona_id_for_query" in text


def test_iris_memory_repository_exposes_persona_filter() -> None:
    """Ensure management reads can apply the same persona isolation as retrieval."""

    source = (
        Path(__file__).resolve().parents[2]
        / "data/plugins/astrbot_plugin_iris_memory/iris_memory/web/repositories/memory_repo.py"
    ).read_text(encoding="utf-8")
    assert "persona_id: Optional[str] = None" in source
    assert 'where_clause["persona_id"] = persona_id' in source
