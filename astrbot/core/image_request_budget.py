"""Request-local visual limits and accounting, independent of model prices."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


class ImageBudgetExceeded(Exception):
    """Stop visual work before an approved retry or turn limit is exceeded."""


class ImageAuthorizationRevoked(ImageBudgetExceeded):
    """Stop an image attempt whose request-local authorization was revoked."""


@dataclass
class ImageRequestScope:
    """Describe one provider operation whose actual factories share a budget."""

    budget: "ImageRequestBudget"
    purpose: str
    provider_id: str
    model: str
    image_count: int = 0
    encoded_bytes: int = 0
    authorization_check: Callable[[], None] | None = None


current_image_request: ContextVar[ImageRequestScope | None] = ContextVar(
    "current_image_request", default=None
)


def image_payload_size(payload: Any) -> tuple[int, int]:
    """Count image submissions and encoded bytes in supported final payloads.

    Args:
        payload: Provider request dictionaries or SDK Pydantic models.

    Returns:
        Image count and base64 payload length, excluding surrounding JSON.
    """
    count = size = 0
    stack = [payload]
    while stack:
        value = stack.pop()
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=True)
        if isinstance(value, (list, tuple)):
            stack.extend(value)
        elif isinstance(value, dict):
            kind = value.get("type")
            if isinstance(kind, str) and kind in {"image_url", "input_image"}:
                source = value.get("image_url", "")
                if isinstance(source, dict):
                    source = source.get("url", "")
                count += 1
                if isinstance(source, str) and source.startswith("data:"):
                    separator = source.find(",")
                    if separator >= 0:
                        if not source.isascii():
                            source[separator + 1 :].encode("ascii")
                        size += len(source) - separator - 1
                continue
            if kind == "image" and isinstance(value.get("source"), dict):
                count += 1
                source = value["source"]
                if source.get("type") == "base64":
                    data = source.get("data", "")
                    if isinstance(data, str):
                        if not data.isascii():
                            data.encode("ascii")
                        size += len(data)
                    else:
                        size += len(data.encode("ascii"))
                continue
            inline = value.get("inline_data", value.get("inlineData"))
            if isinstance(inline, dict) and str(
                inline.get("mime_type", inline.get("mimeType", ""))
            ).startswith("image/"):
                count += 1
                data = inline.get("data", b"")
                size += (
                    4 * ((len(data) + 2) // 3) if isinstance(data, bytes) else len(data)
                )
                continue
            # Only follow message content containers, never tool definitions,
            # JSON schemas, metadata or arbitrary user dictionaries.
            for key in (
                "messages",
                "input",
                "contents",
                "content",
                "parts",
                "contexts",
                "extra_user_content_parts",
            ):
                child = value.get(key)
                if isinstance(child, (dict, list, tuple)):
                    stack.append(child)
    return count, size


@dataclass
class ImageRequestBudget:
    """Account for visual attempts and enforce explicit turn-level limits."""

    max_caption_attempts: int = 2
    max_review_triggers: int | None = None
    max_image_submissions: int | None = None
    caption_attempts: int = 0
    review_triggers: int = 0
    image_submissions: int = 0
    visual_request_attempts: int = 0
    counters: dict = field(default_factory=dict)

    def ensure_attempt_allowed(self, image_count: int, *, purpose: str) -> None:
        """Check caption retry and explicit turn limits before an attempt.

        Args:
            image_count: Images expected in the provider attempt.
            purpose: Main, caption, or review operation.

        Raises:
            ImageBudgetExceeded: A caption retry or explicit turn limit is exhausted.
        """
        if image_count < 0:
            raise ValueError("Negative image budget input")
        if (
            self.max_image_submissions is not None
            and self.image_submissions + image_count > self.max_image_submissions
        ) or (
            purpose == "caption" and self.caption_attempts >= self.max_caption_attempts
        ):
            raise ImageBudgetExceeded("The visual attempt limit is exhausted.")

    def consume_review(self) -> None:
        """Charge an explicit old-image review trigger.

        Raises:
            ImageBudgetExceeded: The turn already used its review triggers.
        """
        if (
            self.max_review_triggers is not None
            and self.review_triggers >= self.max_review_triggers
        ):
            raise ImageBudgetExceeded("The image review limit is exhausted.")
        self.review_triggers += 1

    @contextmanager
    def scope(
        self,
        *,
        purpose: str,
        provider_id: str,
        model: str,
        image_count: int = 0,
        encoded_bytes: int = 0,
        authorization_check: Callable[[], None] | None = None,
    ):
        """Bind a provider operation without modifying shared provider instances.

        Args:
            purpose: Purpose used for separate usage attribution.
            provider_id: Actual configured provider identity.
            model: Actual selected model.
            image_count: Fallback count when a provider reports no final payload.
            encoded_bytes: Fallback size when a provider reports no final payload.
            authorization_check: Synchronous revocation guard for every SDK attempt.

        Yields:
            The request-local scope consumed by provider factory callbacks.
        """
        self.ensure_attempt_allowed(image_count, purpose=purpose)
        scope = ImageRequestScope(
            self,
            purpose,
            provider_id,
            model,
            image_count,
            encoded_bytes,
            authorization_check,
        )
        token = current_image_request.set(scope)
        try:
            yield scope
        finally:
            current_image_request.reset(token)

    def on_attempt(self, scope: ImageRequestScope, payload: Any = None) -> None:
        """Charge immediately before a provider factory without an await boundary.

        Args:
            scope: Active operation provenance and conservative payload size.
            payload: Final SDK payload, when available.
        """
        count, size = (
            (scope.image_count, scope.encoded_bytes)
            if payload is None
            else image_payload_size(payload)
        )
        if count and scope.authorization_check is not None:
            scope.authorization_check()
        self.ensure_attempt_allowed(count, purpose=scope.purpose)
        key = (scope.purpose, scope.provider_id, scope.model)
        group = self.counters.setdefault(
            key,
            {
                "purpose": scope.purpose,
                "provider_id": scope.provider_id,
                "model": scope.model,
                "attempts": 0,
                "image_submissions": 0,
                "encoded_bytes": 0,
                "known_calls": 0,
                "token_usage": {"input_other": 0, "input_cached": 0, "output": 0},
            },
        )
        group["attempts"] += 1
        group["image_submissions"] += count
        group["encoded_bytes"] += size
        self.image_submissions += count
        self.visual_request_attempts += int(count > 0)
        if scope.purpose == "caption":
            self.caption_attempts += 1

    def record_usage(
        self, usage, *, purpose: str, provider_id: str, model: str
    ) -> None:
        """Record reported usage; missing usage remains unknown rather than zero.

        Args:
            usage: Provider TokenUsage, or None when no usage was reported.
            purpose: Operation purpose.
            provider_id: Actual provider.
            model: Actual model.
        """
        group = self.counters.get((purpose, provider_id, model))
        if group is None or usage is None:
            return
        group["known_calls"] += 1
        for name in group["token_usage"]:
            group["token_usage"][name] += getattr(usage, name, 0)

    @property
    def usage_unknown(self) -> bool:
        return any(g["attempts"] > g["known_calls"] for g in self.counters.values())

    def to_dict(self) -> dict:
        """Return JSON-safe counters without inventing prices or missing tokens.

        Returns:
            Totals and separate provider, model, purpose usage groups.
        """
        groups = []
        for value in self.counters.values():
            group = {**value, "token_usage": dict(value["token_usage"])}
            group["unknown_calls"] = max(
                0, group["attempts"] - group.pop("known_calls")
            )
            group["usage_known"] = group["unknown_calls"] == 0
            groups.append(group)
        return {
            "caption_attempts": self.caption_attempts,
            "review_triggers": self.review_triggers,
            "image_submissions": self.image_submissions,
            "usage_unknown": self.usage_unknown,
            "groups": groups,
        }


def charge_image_attempt(payload: Any = None) -> None:
    """Charge a factory only inside an opted-in image operation.

    Args:
        payload: Final request payload, or None to use the scope's accounting hint.
    """
    scope = current_image_request.get()
    if scope is not None:
        scope.budget.on_attempt(scope, payload)
