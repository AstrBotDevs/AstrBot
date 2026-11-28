import json
import re

from .run_context import ContextWrapper
from .tool import FunctionTool, ToolSet

_SEARCH_TERMS = re.compile(r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+")
_STOP_WORDS = {"a", "an", "for", "from", "i", "in", "of", "the", "to", "with"}
_RESULT_LIMIT = 3


def _terms(text: str) -> set[str]:
    terms = set()
    for word in _SEARCH_TERMS.findall(text.casefold()):
        # Overlapping Han bigrams allow partial matches without a word segmenter.
        if "\u3400" <= word[0] <= "\u9fff" and len(word) > 1:
            terms.update(word[i : i + 2] for i in range(len(word) - 1))
        elif word not in _STOP_WORDS:
            terms.add(word)
    return terms


class ToolDiscovery:
    """Expose a fixed bridge to the authorized catalog for one Agent run."""

    def __init__(self, catalog: ToolSet) -> None:
        self.catalog = {tool.name: tool for tool in catalog if tool.active}
        self.seen: set[str] = set()
        self.described: dict[str, FunctionTool] = {}
        self.tools = ToolSet(
            [
                FunctionTool(
                    "astrbot_search_tools",
                    "Find tools for a capability. Describe a matching tool before calling it.",
                    {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 300,
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                ),
                FunctionTool(
                    "astrbot_describe_tool",
                    "Get a tool's complete input schema by name before calling it.",
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                ),
                FunctionTool(
                    "astrbot_call_tool",
                    "Invoke a previously described tool by name with its arguments encoded as a JSON object string.",
                    {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "arguments": {
                                "type": "string",
                                "description": "JSON-encoded argument object, or '{}' for no arguments.",
                            },
                        },
                        "required": ["name", "arguments"],
                        "additionalProperties": False,
                    },
                ),
            ]
        )

    def search(self, context: ContextWrapper, query: str) -> str:
        """Find matching tools without exposing their schemas.

        Args:
            context: Current run and its available tools.
            query: Keywords describing the desired capability.

        Returns:
            A JSON list of new matches, or guidance when none remain.
        """
        terms = _terms(query)
        ranked = []
        for tool in self.catalog.values():
            # Tool names are stronger signals than words in longer descriptions.
            score = 3 * len(terms & _terms(tool.name)) + len(
                terms & _terms(tool.description)
            )
            if score:
                ranked.append((-score, tool.name, tool))

        matches = []
        already_seen = False
        for _, name, tool in sorted(ranked, key=lambda item: item[:2]):
            if not context.is_tool_available(tool):
                continue
            if name in self.seen:
                already_seen = True
                continue
            self.seen.add(name)
            matches.append({"name": name, "description": tool.description[:240]})
            if len(matches) == _RESULT_LIMIT:
                break
        if matches:
            return json.dumps(matches, ensure_ascii=False)
        if already_seen:
            return "No new matching tools. Describe a previous match or try other keywords."
        return "No matching tools. Try a more specific capability or other keywords."

    def describe(self, context: ContextWrapper, name: str) -> str:
        """Describe a currently available tool and record its identity.

        Args:
            context: Current run and its available tools.
            name: Exact name of the tool to describe.

        Returns:
            A JSON object containing the tool's complete definition.

        Raises:
            ValueError: The tool is unavailable in the current catalog.
        """
        tool = self.catalog.get(name)
        if tool is None or not context.is_tool_available(tool):
            raise ValueError("Tool is not available in the current catalog.")
        schema = json.dumps(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
            ensure_ascii=False,
        )
        self.described[name] = tool
        return schema
