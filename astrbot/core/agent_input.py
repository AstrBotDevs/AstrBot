"""Core-owned message preprocessing, independent of runtime history ownership."""

from __future__ import annotations

import asyncio
import datetime
import json
import zoneinfo
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import File, Reply
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.file_extract import extract_file_moonshotai
from astrbot.core.utils.image_input import prepare_request_images
from astrbot.core.utils.media_utils import (
    IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    normalize_model_image_max_size,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

if TYPE_CHECKING:
    from astrbot.core.agent.input import InputComponent
    from astrbot.core.agent.runtime import AgentInput
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.skills.skill_manager import SkillInfo
    from astrbot.core.star.context import Context


class InputProcessingSettings(Protocol):
    """Common message policies supplied independently of native execution settings."""

    provider_settings: dict
    provider_wake_prefix: str
    max_quoted_fallback_images: int
    file_extract_enabled: bool
    file_extract_prov: str
    file_extract_msh_api_key: str
    timezone: str | None


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def apply_prompt_prefix(req: ProviderRequest, cfg: dict) -> None:
    """Apply the configured prefix or prompt template to the current input.

    Args:
        req: Request whose current prompt is updated in place.
        cfg: Provider settings containing the optional prompt prefix.
    """
    prefix = cfg.get("prompt_prefix")
    if not prefix:
        return
    if "{{prompt}}" in prefix:
        req.prompt = prefix.replace("{{prompt}}", req.prompt)
    else:
        req.prompt = f"{prefix}{req.prompt}"


def append_system_reminders(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    timezone: str | None,
) -> None:
    """Append configured sender, group, and time information to the user content.

    Args:
        event: Event providing sender and group details.
        req: Request receiving the additional user content.
        cfg: Provider settings controlling which reminders are included.
        timezone: Configured IANA timezone, or None for the local timezone.
    """
    system_parts: list[str] = []
    if cfg.get("identifier"):
        user_id = event.message_obj.sender.user_id
        user_nickname = event.message_obj.sender.nickname
        system_parts.append(f"User ID: {user_id}, Nickname: {user_nickname}")

    if cfg.get("group_name_display") and event.message_obj.group_id:
        if not event.message_obj.group:
            logger.error(
                "Group name display enabled but group object is None. Group ID: %s",
                event.message_obj.group_id,
            )
        else:
            group_name = event.message_obj.group.group_name
            if group_name:
                system_parts.append(f"Group name: {group_name}")

    if cfg.get("datetime_system_prompt"):
        now = None
        if timezone:
            try:
                now = datetime.datetime.now(zoneinfo.ZoneInfo(timezone))
            except Exception as exc:  # noqa: BLE001
                logger.error("Invalid timezone: %s; using the local timezone.", exc)
        if now is None:
            now = datetime.datetime.now().astimezone()
        current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
        weekday = WEEKDAY_NAMES[now.weekday()]
        system_parts.append(f"Current datetime: {current_time}, Weekday: {weekday}")

    if system_parts:
        system_content = (
            "<system_reminder>" + "\n".join(system_parts) + "</system_reminder>"
        )
        req.extra_user_content_parts.append(TextPart(text=system_content))


async def _apply_file_extract(
    event: AstrMessageEvent,
    req: ProviderRequest,
    config: InputProcessingSettings,
) -> None:
    file_paths = []
    file_names = []
    for comp in event.message_obj.message:
        if isinstance(comp, File):
            file_paths.append(await comp.get_file())
            file_names.append(comp.name)
        elif isinstance(comp, Reply) and comp.chain:
            for reply_comp in comp.chain:
                if isinstance(reply_comp, File):
                    file_paths.append(await reply_comp.get_file())
                    file_names.append(reply_comp.name)
    if not file_paths:
        return
    if not req.prompt:
        req.prompt = "总结一下文件里面讲了什么？"
    if config.file_extract_prov == "moonshotai":
        if not config.file_extract_msh_api_key:
            logger.error("Moonshot AI API key for file extract is not set")
            return
        file_contents = await asyncio.gather(
            *[
                extract_file_moonshotai(
                    file_path,
                    config.file_extract_msh_api_key,
                )
                for file_path in file_paths
            ]
        )
    else:
        logger.error("Unsupported file extract provider: %s", config.file_extract_prov)
        return

    for file_content, file_name in zip(file_contents, file_names):
        req.contexts.append(
            {
                "role": "system",
                "content": (
                    "File Extract Results of user uploaded files:\n"
                    f"{file_content}\nFile Name: {file_name or 'Unknown'}"
                ),
            },
        )


def matches_provider_wake_prefix(
    event: AstrMessageEvent,
    provider_wake_prefix: str,
) -> bool:
    """Return whether an event satisfies the provider wake prefix.

    Args:
        event: Incoming event whose message and platform should be inspected.
        provider_wake_prefix: Prefix required by the provider, if any.

    Returns:
        True for programmatic wakeups, when no prefix is configured, when
        WebChat is exempt, or when the message starts with the prefix.
    """
    message_str = event.message_str or ""
    if event.get_platform_name() == "lark":
        message_str = message_str.lstrip()
    return (
        isinstance(event, AgentWakeupEvent)
        or not provider_wake_prefix
        or event.get_platform_name() == "webchat"
        or message_str.startswith(provider_wake_prefix)
    )


@dataclass(slots=True)
class CollectedInput:
    """Core's collected input and quote identity, before model adaptation."""

    request: ProviderRequest
    quote_image_ref: str | None = None
    quoted_image_refs: set[str] = field(default_factory=set)
    parse_quoted: bool = True
    source_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreparedRequest:
    """Request content and the media state reused during finalization."""

    request: ProviderRequest
    images: dict[str, dict] = field(default_factory=dict)
    captioned_refs: set[str] = field(default_factory=set)
    image_max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE


async def prepare_input_content(
    event: AstrMessageEvent,
    plugin_context: Context,
    config: InputProcessingSettings,
    provider: Provider,
    req: ProviderRequest,
    *,
    collected_request: bool,
    quote_image_ref: str | None,
    quoted_image_refs: set[str],
) -> PreparedRequest | None:
    """Apply Core's input policies to collected content, never loading history.

    Args:
        event: Message source and temporary attachment owner.
        plugin_context: Host services for media conversion and captioning.
        config: Common input processing settings.
        provider: Selected model's capabilities for media adaptation.
        req: Current input buffer; existing context is supplied by the runtime.
        collected_request: Whether quoting and prompt templates need processing.
        quote_image_ref: Embedded quoted image selected during collection.
        quoted_image_refs: All collected quoted images.

    Returns:
        Processed input and reusable media preparation state, or None for empty input.
    """
    from astrbot.core import agent_media as media
    from astrbot.core.provider import capabilities as providers

    # A background task may be stopped while conversation loading is pending.
    stop_signal = event.get_extra("_background_stop_signal")
    if isinstance(stop_signal, asyncio.Event) and stop_signal.is_set():
        return None

    cfg = config.provider_settings
    options = cfg.get("image_compress_options", {})
    max_size = normalize_model_image_max_size(
        options.get("max_size") if isinstance(options, dict) else None
    )
    prepared_images: dict[str, dict] = {}
    supports_image = providers.supports_modality(provider, "image")
    caption_provider_id = cfg.get("default_image_caption_provider_id") or ""
    if (
        supports_image
        or not caption_provider_id
        or (req.conversation and req.image_urls)
    ):
        quote_image_ref = None
    await prepare_request_images(
        req,
        event,
        max_size=max_size,
        prepared=prepared_images,
        quote_image_ref=quote_image_ref,
        quoted_refs=quoted_image_refs,
        finalize=False,
    )

    if isinstance(req.contexts, str):
        req.contexts = json.loads(req.contexts)
    thread_selected_text = event.get_extra("thread_selected_text")
    if isinstance(thread_selected_text, str) and thread_selected_text.strip():
        req.extra_user_content_parts.append(
            TextPart(
                text=(
                    "The user is asking in a side thread about this selected "
                    "excerpt from the previous assistant answer:\n"
                    f"<selected_excerpt>{thread_selected_text.strip()}</selected_excerpt>"
                )
            )
        )
    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    req.audio_urls = normalize_and_dedupe_strings(req.audio_urls)

    if config.file_extract_enabled:
        try:
            await _apply_file_extract(event, req, config)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while applying file extract: %s", exc)

    has_reply = any(isinstance(comp, Reply) for comp in event.message_obj.message)

    if not req.prompt and not req.image_urls and not req.audio_urls:
        if has_reply or req.extra_user_content_parts:
            req.prompt = "<attachment>"
        else:
            return None

    captioned_refs: set[str] = set()
    montage_refs = {
        result["path"]
        for result in prepared_images.values()
        if result["path"] and result["montage"]
    }
    if collected_request:
        captioned_ref = await media.append_quoted_content(
            event,
            req,
            cfg.get("default_image_caption_provider_id") or "",
            plugin_context,
            media.get_quoted_message_settings(cfg),
            main_provider_supports_image=providers.supports_modality(provider, "image"),
            skip_quote_image_caption=bool(req.conversation and req.image_urls),
            image_ref=prepared_images[quote_image_ref]["path"]
            if quote_image_ref
            else None,
            image_is_montage=bool(
                quote_image_ref and prepared_images[quote_image_ref]["montage"]
            ),
        )
        if captioned_ref:
            captioned_refs.add(captioned_ref)
    apply_prompt_prefix(req, cfg)
    if (
        req.conversation
        and caption_provider_id
        and req.image_urls
        and not supports_image
    ):
        captioned_refs.update(
            await media.caption_request_images(
                event,
                req,
                cfg,
                plugin_context,
                caption_provider_id,
                montage_refs=montage_refs,
            )
        )
    if not req.session_id:
        req.session_id = event.unified_msg_origin
    append_system_reminders(event, req, cfg, config.timezone)
    return PreparedRequest(req, prepared_images, captioned_refs, max_size)


def collect_plugin_capabilities(
    context: Context, event: AstrMessageEvent
) -> tuple[ToolSet, list[SkillInfo]]:
    """Collect enabled plugin contributions without applying a runtime persona.

    Args:
        context: Core tool and skill registries.
        event: Current source's plugin selection.

    Returns:
        Authorized non-builtin tools and plugin-owned skills. Runtime-owned
        controls, installed skills and workspace skills are composed separately.
    """
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.skills.skill_manager import SkillManager
    from astrbot.core.star.agent_capabilities import filter_skills, filter_tools

    registered = context.get_llm_tool_manager().get_full_tool_set()
    tools = ToolSet(tools=list(registered))
    tools = filter_tools(event, tools)
    settings = context.get_config(umo=event.unified_msg_origin).get(
        "provider_settings", {}
    )
    try:
        skills = SkillManager().list_skills(
            active_only=True, runtime=settings.get("computer_use_runtime", "none")
        )
        skills = filter_skills(
            [skill for skill in skills if skill.source_type == "plugin"],
            {
                **settings,
                "plugin_set": event.plugins_name
                if event.plugins_name is not None
                else ["*"],
            },
        )
    except Exception:
        logger.exception("Failed to collect plugin skills for an agent input")
        skills = []
    return tools, skills


async def prepare_agent_input(
    context: Context,
    event: AstrMessageEvent,
    *,
    provider_wake_prefix: str = "",
    streaming: bool | None = None,
    content: list[InputComponent] | None = None,
) -> AgentInput | None:
    """Admit an input without constructing a runtime-specific model request.

    Args:
        context: Core configuration and plugin services.
        event: Platform or programmatic input with trusted caller identity.
        provider_wake_prefix: Core-resolved additional AI trigger prefix.
        streaming: Core output preference for this input, or runtime default.
        content: Explicit portable content; None preserves the source event.

    Returns:
        Authorized common input, or None when rejected. Queued dispatch must
        recheck admission through admit_agent_input before execution.
    """
    from astrbot.core.agent.input import PlainInput
    from astrbot.core.agent.runtime import AgentInput, AgentPermissions
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.star.star_handler import EventType

    if await call_event_hook(event, EventType.OnWaitingLLMRequestEvent):
        return None
    if event.get_extra("provider_request") is None and not matches_provider_wake_prefix(
        event, provider_wake_prefix
    ):
        return None
    if (
        content is None
        and event.get_extra("provider_request") is None
        and provider_wake_prefix
        and not isinstance(event, AgentWakeupEvent)
    ):
        text = event.message_str or ""
        if event.get_platform_name() == "lark":
            text = text.lstrip()
        if text.startswith(provider_wake_prefix):
            text = text[len(provider_wake_prefix) :]
            # Platform text is already typed; preserve its formatting and whitespace.
            content = [PlainInput.model_construct(text=text)] if text else []
    for component in event.message_obj.message:
        if isinstance(component, File):
            await component.get_file()
        elif isinstance(component, Reply) and component.chain:
            for quoted in component.chain:
                if isinstance(quoted, File):
                    await quoted.get_file()
    input = AgentInput(
        event=event,
        permissions=AgentPermissions.from_event(event),
        content=content,
        streaming=streaming,
    )
    if not await admit_agent_input(context, input):
        return None
    return input


async def admit_agent_input(context: Context, input: AgentInput) -> bool:
    """Recheck Core policy and refresh capabilities at execution admission.

    Args:
        context: Current configuration and plugin services.
        input: Input whose caller authorization must reflect the current policy.

    Returns:
        Whether the input remains authorized to execute.
    """
    from astrbot.core.agent.runtime import AgentPermissions
    from astrbot.core.star.session_llm_manager import SessionServiceManager

    event = input.event
    current_config = context.get_config(umo=event.unified_msg_origin)
    if (
        event.is_stopped()
        or not current_config.get("provider_settings", {}).get("enable", True)
        or not await SessionServiceManager.should_process_llm_request(event)
    ):
        return False
    enabled = current_config.get("plugin_set", ["*"])
    event.plugins_name = None if enabled == ["*"] else list(enabled)
    input.permissions = AgentPermissions.from_event(event)
    input.plugin_tools, input.plugin_skills = collect_plugin_capabilities(
        context, event
    )
    return True
