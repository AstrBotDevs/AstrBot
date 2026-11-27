import re

from .run_context import ContextWrapper
from .tool import FunctionTool, TContext, ToolSet

_SEARCH_TERMS = re.compile(r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+")
_STOP_WORDS = {"a", "an", "for", "from", "i", "in", "of", "the", "to", "with"}
_RESULT_LIMIT = 3


def _terms(text: str) -> set[str]:
    terms = set()
    for word in _SEARCH_TERMS.findall(text.casefold()):
        if "\u3400" <= word[0] <= "\u9fff" and len(word) > 1:
            terms.update(word[i : i + 2] for i in range(len(word) - 1))
        elif word not in _STOP_WORDS:
            terms.add(word)
    return terms


class ToolDiscovery(FunctionTool[TContext]):
    """Search the request's tools and make the matches available for later rounds."""

    def __init__(self, catalog: ToolSet) -> None:
        name = "astrbot_search_tools"
        names = set(catalog.names())
        suffix = 1
        while name in names:
            name = f"astrbot_search_tools_{suffix}"
            suffix += 1
        super().__init__(
            name=name,
            description=(
                "Find and load tools by describing the capability you need. "
                "Use this when a task needs a tool you have not been given yet. "
                "The next request will include full definitions for the best matches."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                        "description": "Capability to find, with action and domain keywords.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )
        self.catalog = tuple(tool for tool in catalog if tool.active)
        self.loaded: dict[str, FunctionTool] = {}

    async def call(self, context: ContextWrapper[TContext], **kwargs) -> str:
        query = _terms(kwargs["query"])
        ranked = []
        for tool in self.catalog:
            score = 3 * len(query & _terms(tool.name)) + len(
                query & _terms(tool.description)
            )
            if score:
                ranked.append((-score, tool.name, tool))

        matches = []
        for _, name, tool in sorted(ranked, key=lambda item: item[:2]):
            if not tool.is_available():
                continue
            self.loaded[name] = tool
            matches.append(name)
            if len(matches) == _RESULT_LIMIT:
                break
        if not matches:
            return (
                "No matching tools. Try a more specific capability or other keywords."
            )
        return f"Loaded tools for the next round: {', '.join(matches)}."
