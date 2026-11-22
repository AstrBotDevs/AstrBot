"""Legacy ChatUI view declarations and results (`astrbot.api.chatui`)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ...results import Propagation
from ...results import ViewResult as SDKViewResult

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
ViewTarget = Literal[
    "chat_message",
    "chat_workbench",
    "chat_workbench_with_launcher",
    "plugin_page",
]


@dataclass
class ViewSpec:
    """Declare a ChatUI view host target and permitted actions."""

    name: str
    target: ViewTarget = "plugin_page"
    title: str = ""
    description: str = ""
    version: int = 1
    actions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"Invalid view name: {self.name!r}")
        if self.version < 1:
            raise ValueError("ViewSpec version must be >= 1")
        if self.target == "plugin_page" and self.actions:
            raise ValueError(
                "Standalone views use plugin Web APIs, not UI interaction actions."
            )

    @property
    def entry(self) -> Path:
        """Return the conventional entry HTML path relative to plugin root."""
        return Path("views") / self.name / "index.html"

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-compatible declaration dict."""
        return {
            "name": self.name,
            "target": self.target,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "actions": list(self.actions),
        }


@dataclass
class ViewResult:
    """Create a named ChatUI card or update the current interaction's card."""

    data: dict[str, Any]
    name: str | None = None
    text: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        if self.name is not None and (not self.name or not self.text.strip()):
            raise ValueError("Creating a view requires a name and fallback text.")
        if self.name is None and self.text:
            raise ValueError("A view update cannot replace the tool's text result.")
        if self.name is None and self.title:
            raise ValueError("A view update cannot replace its title.")
        encoded = json.dumps(self.data, allow_nan=False, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise ValueError("View data exceeds one MiB.")
        self.data = json.loads(encoded)

    def to_sdk_result(
        self,
        *,
        propagation: Propagation = Propagation.CONTINUE,
    ) -> SDKViewResult:
        """Convert this legacy ViewResult to the wire-level SDK ViewResult."""
        return SDKViewResult(
            propagation=propagation,
            name=self.name,
            data=dict(self.data),
            text=self.text,
            title=self.title,
        )


__all__ = ["ViewResult", "ViewSpec"]
