import ast
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "astrbot"
    / "core"
    / "config"
    / "default.py"
)


def _dict_value(node: ast.AST, key: str) -> ast.AST | None:
    if not isinstance(node, ast.Dict):
        return None
    for name, value in zip(node.keys, node.values):
        if isinstance(name, ast.Constant) and name.value == key:
            return value
    return None


def test_llmtr_chat_completion_template():
    tree = ast.parse(SRC.read_text())
    metadata = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CONFIG_METADATA_2":
                    metadata = node.value
    assert metadata is not None

    tmpl_node = metadata
    for key in (
        "provider_group",
        "metadata",
        "provider",
        "config_template",
        "LLMTR",
    ):
        tmpl_node = _dict_value(tmpl_node, key)
        assert tmpl_node is not None, f"missing key {key}"

    tmpl = ast.literal_eval(tmpl_node)
    assert tmpl["id"] == "llmtr"
    assert tmpl["provider"] == "llmtr"
    assert tmpl["type"] == "openai_chat_completion"
    assert tmpl["provider_type"] == "chat_completion"
    assert tmpl["api_base"] == "https://llmtr.com/v1"
    assert tmpl["timeout"] == 120
