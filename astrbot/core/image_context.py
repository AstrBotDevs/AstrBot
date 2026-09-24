"""Server-owned images for one internal-agent turn, without model-visible grants."""

import copy
import uuid
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.message import (
    ContentPart,
    ImageRefPart,
    ImageURLPart,
    Message,
    TextPart,
)
from astrbot.core.db.po import ConversationImageRef
from astrbot.core.image_asset_store import (
    ImageAssetStore,
    ImageStorageLimitError,
    ImageValidationError,
    run_image_io,
    validate_image_source,
)
from astrbot.core.image_request_budget import (
    ImageAuthorizationRevoked,
    ImageBudgetExceeded,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    MediaResolver,
    is_recoverable_image_error,
    prepare_model_image,
)

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

MAX_CONTEXT_IMAGE_PIXELS = 20_000_000
MAX_CONTEXT_IMAGE_FRAMES = 100


@dataclass(frozen=True)
class ImageRegeneration:
    """Carry an internal regeneration grant; JSON dictionaries cannot create one."""

    conversation_id: str
    checkpoint_id: str
    occurrence_ids: tuple[str, ...]


class ImageTurnContext:
    """Track pending visual inputs separately from persisted lightweight references."""

    _active_contexts: weakref.WeakSet["ImageTurnContext"] = weakref.WeakSet()

    def __init__(self, db: "BaseDatabase", conversation_id: str, checkpoint_id: str):
        """Create request-local state without granting access to any image.

        Args:
            db: Active application database.
            conversation_id: Server-selected conversation identity.
            checkpoint_id: Server-selected current turn identity.
        """
        self.db = db
        self.conversation_id = conversation_id
        self.checkpoint_id = checkpoint_id
        self.references: dict[str, ConversationImageRef] = {}
        self.pending_visuals: dict[str, str] = {}
        self.notices: list[str] = []
        self.cached_parts: dict[tuple[bool, str], ContentPart] = {}
        self.capture_results: dict[tuple[bool, str], dict] = {}
        self.part_visual_keys: dict[int, str] = {}
        self._hook_parts: dict[int, tuple[object, object]] = {}
        self._hook_checkpoints: dict[int, list[dict]] = {}
        self._hook_legacy_remaining: list[dict] = []
        self.configured = False
        self.preview_cache: dict[str, str] = {}
        self.preview_representations: dict[str, str] = {}
        self.retrieval_visuals: set[str] = set()
        self.description_attempted: set[str] = set()
        self.persisted_references: dict[str, ConversationImageRef] = {}
        self.revoked = False
        self.revoked_occurrences: set[str] = set()
        self._active_contexts.add(self)

    @classmethod
    def notify_committed_change(
        cls,
        db,
        conversation_id,
        *,
        deleted=False,
        revoked_occurrences=(),
        revoked_checkpoints=(),
        persisted_references=(),
    ) -> None:
        """Invalidate live requests only after the matching database commit succeeds.

        Args:
            db: Database whose metadata transaction committed.
            conversation_id: Conversation affected by the committed change.
            deleted: Whether the entire conversation was deleted.
            revoked_occurrences: Image occurrences removed by an explicit edit.
            revoked_checkpoints: Turns invalidated by editing or regeneration.
            persisted_references: Newly committed current-turn associations.
        """
        db_path = getattr(db, "db_path", None)
        for context in list(cls._active_contexts):
            same_db = context.db is db
            other_path = getattr(context.db, "db_path", None)
            if isinstance(db_path, (str, Path)) and isinstance(other_path, (str, Path)):
                if str(db_path) != ":memory:" and str(other_path) != ":memory:":
                    same_db = Path(db_path).resolve() == Path(other_path).resolve()
            if not same_db or context.conversation_id != conversation_id:
                continue
            if deleted or context.checkpoint_id in revoked_checkpoints:
                context.revoked = True
            context.revoked_occurrences.update(revoked_occurrences)
            for ref in persisted_references:
                if ref.occurrence_id in context.references:
                    context.persisted_references[ref.occurrence_id] = ref

    def check_visual_authorization(self, occurrence_ids) -> None:
        """Check revocation immediately before each SDK factory, without I/O.

        Args:
            occurrence_ids: Exact image identities included in this SDK operation.

        Raises:
            ImageAuthorizationRevoked: A selected image or its active turn was revoked.
        """
        if occurrence_ids and (
            self.revoked or self.revoked_occurrences.intersection(occurrence_ids)
        ):
            raise ImageAuthorizationRevoked("Image authorization was revoked.")

    async def authorize_visuals(self, occurrence_ids) -> set[str]:
        """Resolve stored grants in batches while preserving unsaved current images.

        Args:
            occurrence_ids: Candidate images for the next provider request.

        Returns:
            Currently authorized occurrence IDs. Current inputs require no database row.
        """
        if self.revoked:
            return set()
        candidates = set(occurrence_ids) - self.revoked_occurrences
        current = (
            set(self.references) | (set(self.pending_visuals) - self.retrieval_visuals)
        ) - set(self.persisted_references)
        authorized = candidates & current
        stored = list(candidates - current)
        for offset in range(0, len(stored), 100):
            rows = await self.db.get_conversation_images(
                self.conversation_id,
                stored[offset : offset + 100],
                user_id=self.user_id,
                platform_id=self.platform_id,
                available_only=True,
            )
            authorized.update(row.occurrence_id for row in rows)
        if self.revoked:
            return set()
        return authorized - self.revoked_occurrences

    def configure(
        self,
        *,
        user_id,
        platform_id,
        event,
        max_size,
        provider,
        model=None,
        caption_provider=None,
        caption_model=None,
        budget=None,
        caption_explicit=False,
    ) -> None:
        """Bind trusted execution identity and the explicitly selected providers.

        Args:
            user_id: Server-selected conversation owner.
            platform_id: Server-selected platform.
            event: Owner of temporary files.
            max_size: Model preview edge limit.
            provider: Current main provider.
            model: Current explicit main model.
            caption_provider: Selected description provider, or None if unavailable.
            caption_model: Explicit description model override.
            budget: Shared request/turn accounting object.
            caption_explicit: Whether an explicitly configured provider must remain fixed.
        """
        self.user_id, self.platform_id = user_id, platform_id
        self.event, self.max_size = event, max_size
        self.provider, self.model = provider, model
        self.caption_provider, self.caption_model = caption_provider, caption_model
        self.budget = budget
        self.caption_explicit = caption_explicit
        self.configured = True

    async def get_reference(self, occurrence_id: str) -> ConversationImageRef | None:
        """Resolve only current trusted inputs or currently authorized stored references.

        Args:
            occurrence_id: Conversation-scoped image identity.

        Returns:
            Authorized metadata, or None for unavailable references.
        """
        if self.revoked or occurrence_id in self.revoked_occurrences:
            return None
        if (
            occurrence_id in self.references
            and occurrence_id not in self.persisted_references
        ):
            return self.references[occurrence_id]
        rows = await self.db.get_conversation_images(
            self.conversation_id,
            [occurrence_id],
            user_id=self.user_id,
            platform_id=self.platform_id,
        )
        if self.revoked or occurrence_id in self.revoked_occurrences:
            return None
        return rows[0] if rows else None

    async def open_preview(self, occurrence_id: str) -> str:
        """Prepare an event-owned preview without importing a second permanent asset.

        Args:
            occurrence_id: Authorized occurrence selected in this conversation.

        Returns:
            Local temporary preview path.

        Raises:
            PermissionError: The reference is no longer authorized.
            OSError: The stored original or preview is unavailable.
        """
        reference = await self.get_reference(occurrence_id)
        if reference is None:
            raise PermissionError("Image is unavailable in this conversation")
        if occurrence_id in self.preview_cache:
            return self.preview_cache[occurrence_id]
        if occurrence_id in self.pending_visuals:
            path = self.pending_visuals[occurrence_id]
            self.preview_cache[occurrence_id] = path
            return path
        store = ImageAssetStore(
            self.db,
            max_pixels=MAX_CONTEXT_IMAGE_PIXELS,
            max_frames=MAX_CONTEXT_IMAGE_FRAMES,
        )
        target = Path(get_astrbot_temp_path()) / f"image-review-{uuid.uuid4()}.img"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.event.track_temporary_local_file(str(target))

        def copy_original(stream, destination, stop):
            with destination.open("xb") as output:
                while not stop.is_set():
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        return
                    output.write(chunk)
                raise OSError("Image preparation cancelled")

        async with store.open_image(
            conversation_id=self.conversation_id,
            occurrence_id=occurrence_id,
            user_id=self.user_id,
            platform_id=self.platform_id,
        ) as stream:
            await run_image_io(copy_original, stream, target)
        prepared = await prepare_model_image(
            str(target),
            max_size=self.max_size,
            output_dir=Path(get_astrbot_temp_path()),
        )
        if prepared is None:
            raise OSError("Image preview unavailable")
        path, montage, cleanup, _ = prepared
        if cleanup:
            self.event.track_temporary_local_file(path)
        self.preview_cache[occurrence_id] = path
        self.preview_representations[occurrence_id] = (
            "animation_montage" if montage else "model_preview"
        )
        self.persisted_references[occurrence_id] = reference
        return path

    async def catalog(self, *, query=None, cursor=None, source_message_id=None):
        """List bounded authorized metadata without reading image files.

        Args:
            query: Optional literal description search.
            cursor: Last sequence and occurrence returned by a prior page.
            source_message_id: Optional exact platform reply target.

        Returns:
            Bounded entries and the next cursor; paths and asset IDs are omitted.
        """
        rows, next_cursor = await self.db.list_conversation_images(
            self.conversation_id,
            user_id=self.user_id,
            platform_id=self.platform_id,
            limit=20,
            cursor=cursor,
            query=query,
            source_message_id=source_message_id,
        )
        entries = [
            {
                key: row.get(key)
                for key in (
                    "occurrence_id",
                    "source_message_id",
                    "image_index",
                    "checkpoint_sequence",
                    "description",
                    "description_status",
                    "user_annotation",
                    "asset_state",
                )
            }
            for row in rows
        ]
        return {"images": entries, "next_cursor": next_cursor}

    async def prepare_step(self, provider, model=None) -> None:
        """Describe unprocessed current inputs and bind the active provider.

        Args:
            provider: Actual provider for this attempt, including fallbacks.
            model: Explicit model override for this attempt.
        """
        self.provider, self.model = provider, model
        if not self.configured:
            return
        modalities = provider.provider_config.get("modalities")
        if modalities and "tool_use" not in modalities:
            notice = "The active model cannot call image catalog or review tools. Use available descriptions and explicitly injected images; ask for clarification when a target is ambiguous."
            if notice not in self.notices:
                self.notices.append(notice)
        if not self.caption_explicit:
            modalities = provider.provider_config.get("modalities")
            self.caption_provider = (
                provider if not modalities or "image" in modalities else None
            )
            self.caption_model = model
        if self.caption_provider is None:
            return
        from astrbot.core.image_description import describe_images

        pending = [
            occurrence
            for occurrence in self.pending_visuals
            if occurrence in self.references
            and occurrence not in self.description_attempted
        ]
        if pending:
            self.description_attempted.update(pending)
            try:
                await describe_images(
                    self,
                    self.caption_provider,
                    model=self.caption_model,
                    occurrence_ids=pending,
                )
            except ImageBudgetExceeded:
                self.notices.append(
                    "The image description budget is exhausted; remaining descriptions are pending."
                )

    async def project_messages(self, messages: list[Message]) -> list[Message]:
        """Project fresh authorized descriptions without mutating persistent messages.

        Args:
            messages: Current runner messages, including lightweight references.

        Returns:
            Same ordered messages with reference content projected to ordinary text.
        """
        projected = copy.deepcopy(messages)
        ids = list(
            dict.fromkeys(
                part.occurrence_id
                for message in messages
                if isinstance(message.content, list)
                for part in message.content
                if isinstance(part, ImageRefPart)
                and (
                    part.occurrence_id not in self.references
                    or part.occurrence_id in self.persisted_references
                )
            )
        )
        authorized = {
            key: ref
            for key, ref in self.references.items()
            if key not in self.persisted_references
        }
        for offset in range(0, len(ids), 100):
            rows = await self.db.get_conversation_images(
                self.conversation_id,
                ids[offset : offset + 100],
                user_id=self.user_id,
                platform_id=self.platform_id,
            )
            authorized.update({row.occurrence_id: row for row in rows})
        if self.revoked:
            authorized.clear()
        for key in self.revoked_occurrences:
            authorized.pop(key, None)
        for message in projected:
            if not isinstance(message.content, list):
                continue
            parts = []
            for part in message.content:
                if isinstance(part, ImageRefPart):
                    ref = authorized.get(part.occurrence_id)
                    text = f"[Image reference: {part.occurrence_id}; unavailable]"
                    if ref is not None:
                        text = (
                            f"[Image reference: {ref.occurrence_id}; description status: "
                            f"{ref.description_status}]\n{ref.description}"
                        )
                        if ref.user_annotation:
                            text += f"\n[User annotation, separate from model observation]\n{ref.user_annotation}"
                    part = TextPart(text=text)
                parts.append(part)
            message.content = parts
        return projected

    async def previous_input(self, history: list[dict]) -> str | None:
        """Resolve a unique user image in the most recent visible complete turn.

        Args:
            history: Server-loaded history including checkpoint boundaries.

        Returns:
            An authorized occurrence, or None when absent or ambiguous.
        """
        end = next(
            (
                index
                for index in range(len(history) - 1, -1, -1)
                if history[index].get("role") == "_checkpoint"
            ),
            None,
        )
        if end is None:
            return None
        start = next(
            (
                index + 1
                for index in range(end - 1, -1, -1)
                if history[index].get("role") == "_checkpoint"
            ),
            0,
        )
        occurrences = list(
            dict.fromkeys(
                part.get("occurrence_id")
                for message in history[start:end]
                if message.get("role") == "user"
                and isinstance(message.get("content"), list)
                for part in message["content"]
                if isinstance(part, dict) and part.get("type") == "image_ref"
            )
        )
        if len(occurrences) != 1:
            return None
        reference = await self.get_reference(occurrences[0])
        return reference.occurrence_id if reference else None

    async def read_existing(
        self, occurrence_id, *, question="", refresh_description=False
    ):
        """Queue a controlled reread, or answer through the selected caption model.

        Args:
            occurrence_id: Conversation-scoped target.
            question: Optional directed visual question.
            refresh_description: Explicit request for a new structured observation.

        Returns:
            Tool-visible text; image bytes remain in the transient request queue.
        """
        from astrbot.core.image_description import describe_images

        reference = await self.get_reference(occurrence_id)
        if reference is None:
            return "Image is unavailable in this conversation."
        try:
            self.budget.consume_review()
        except ImageBudgetExceeded:
            self.notices.append(
                "The image review limit for this turn has been reached."
            )
            return "Image review limit reached; use existing descriptions or ask in another turn."
        try:
            preview = await self.open_preview(occurrence_id)
        except (PermissionError, OSError, ValueError) as exc:
            if isinstance(exc, OSError) and not is_recoverable_image_error(exc):
                raise
            return "The authorized image original is currently unavailable."
        modalities = self.provider.provider_config.get("modalities")
        visual = not modalities or "image" in modalities
        if refresh_description or not visual:
            if self.caption_provider is None:
                return (
                    "No configured visual description provider is available. Existing description: "
                    + reference.description
                )
            try:
                answer = await describe_images(
                    self,
                    self.caption_provider,
                    model=self.caption_model,
                    question=question or None,
                    occurrence_ids=[occurrence_id],
                    refresh=refresh_description,
                )
            except ImageBudgetExceeded:
                self.notices.append("The image description budget is exhausted.")
                return "Image description budget exhausted; no additional visual request was sent."
            if not visual:
                return (
                    answer
                    or "The requested image description is available in the image catalog."
                )
        if self.revoked or occurrence_id in self.revoked_occurrences:
            return "Image is unavailable in this conversation."
        self.pending_visuals[occurrence_id] = preview
        self.retrieval_visuals.add(occurrence_id)
        return "The authorized image is queued for the next visual step."

    async def update_note(self, occurrence_id: str, annotation: str) -> str:
        """Store an explicit user correction independently of model observations.

        Args:
            occurrence_id: Authorized occurrence.
            annotation: User-provided correction, not a generated observation.

        Returns:
            Status without exposing private asset metadata.
        """
        if not isinstance(annotation, str) or len(annotation) > 4096:
            return "User annotation must be at most 4096 characters."
        ref = await self.get_reference(occurrence_id)
        if ref is None:
            return "Image is unavailable in this conversation."
        if (
            occurrence_id in self.references
            and occurrence_id not in self.persisted_references
        ):
            ref.user_annotation = annotation
            return "User annotation updated separately from the image description."
        updated = await self.db.update_image_annotation(
            self.conversation_id,
            occurrence_id,
            user_id=self.user_id,
            platform_id=self.platform_id,
            expected_checkpoint_id=ref.checkpoint_id,
            expected_annotation=ref.user_annotation,
            annotation=annotation,
        )
        return (
            "User annotation updated."
            if updated
            else "Image changed; obtain its latest catalog entry before retrying."
        )

    async def capture(
        self,
        ref: str,
        *,
        temporary: bool = False,
        reuse: bool = False,
        source_message_id: str | None = None,
        image_index: int = 0,
        max_size: int,
        event: "AstrMessageEvent",
    ) -> ContentPart:
        """Capture originals before decoding previews, or validate a transient fallback.

        Args:
            ref: Newly supplied local, remote, or encoded image reference.
            temporary: Whether this image must remain request-only.
            reuse: Reuse a preparation-pass result; tool inputs default to fresh capture.
            source_message_id: Platform message identity when available.
            image_index: Appearance order in its source message.
            max_size: Longest edge for the model preview.
            event: Owner of transient preview/source files.

        Returns:
            A lightweight image reference, temporary text marker, or failure marker.
        """
        if self.revoked:
            return TextPart(
                text="[Image unavailable: this conversation turn was revoked]"
            )
        cache_key = (temporary, ref)
        if reuse and cache_key in self.cached_parts:
            return self.cached_parts[cache_key]
        occurrence = str(uuid.uuid4())
        asset = None
        storage_notice = None
        result = {
            "path": None,
            "original_path": "",
            "montage": False,
            "status": None,
            "temporary": temporary,
            "notices": [],
            "quoted": False,
        }
        try:
            async with MediaResolver(ref, media_type="image").as_path() as source:
                model_source = source.path
                if not temporary:
                    try:
                        store = ImageAssetStore(
                            self.db,
                            max_pixels=MAX_CONTEXT_IMAGE_PIXELS,
                            max_frames=MAX_CONTEXT_IMAGE_FRAMES,
                        )
                        asset = await store.import_file(source.path)
                        model_source = store.root / asset.storage_key
                    except ImageValidationError:
                        raise
                    except (OSError, SQLAlchemyError) as exc:
                        if isinstance(exc, OSError) and not is_recoverable_image_error(
                            exc
                        ):
                            raise
                        storage_notice = "The image original could not be saved because storage is unavailable. It is available only for the current request."
                if asset is None:
                    await run_image_io(
                        validate_image_source,
                        source.path,
                        MAX_CONTEXT_IMAGE_PIXELS,
                        MAX_CONTEXT_IMAGE_FRAMES,
                    )
                preview = await prepare_model_image(
                    str(model_source),
                    max_size=max_size,
                    output_dir=Path(get_astrbot_temp_path()),
                )
                if preview is None:
                    raise ImageValidationError("Image preview is unavailable")
                preview_path, montage, needs_cleanup, _ = preview
                if needs_cleanup:
                    event.track_temporary_local_file(preview_path)
                elif asset is None:
                    # The resolver may own the exact file returned as an unchanged preview.
                    for owned in source.cleanup_paths:
                        event.track_temporary_local_file(str(owned))
                    source.detach()
                if self.revoked:
                    return TextPart(
                        text="[Image unavailable: this conversation turn was revoked]"
                    )
                result.update(path=preview_path, montage=montage)
                if storage_notice:
                    self.notices.append(storage_notice)
                self.pending_visuals[occurrence] = preview_path
                self.preview_cache[occurrence] = preview_path
                self.preview_representations[occurrence] = (
                    "animation_montage" if montage else "model_preview"
                )
                if asset is not None:
                    association = ConversationImageRef(
                        conversation_id=self.conversation_id,
                        occurrence_id=occurrence,
                        asset_id=asset.asset_id,
                        checkpoint_id=self.checkpoint_id,
                        source_message_id=source_message_id,
                        image_index=image_index,
                    )
                    self.references[occurrence] = association
                    part = ImageRefPart(
                        occurrence_id=occurrence, asset_id=asset.asset_id
                    )
                else:
                    part = TextPart(
                        text="[Image supplied for this request only]"
                    ).mark_as_temp()
                self.part_visual_keys[id(part)] = occurrence
        except (ImageStorageLimitError, ImageValidationError, ValueError):
            self.notices.append(
                "The image original was stored, but its model preview could not be prepared. It was not sent to the model or attached to this conversation."
                if asset is not None
                else "An image was rejected because it is invalid or exceeds the image input limits. It was not sent to the model or saved in the image catalog."
            )
            result["status"] = "unavailable"
            part = TextPart(text="[Image unavailable]")
        except Exception as exc:
            if not is_recoverable_image_error(exc):
                raise
            self.notices.append(
                "The image original was stored, but its model preview could not be read. It was not sent to the model or attached to this conversation."
                if asset is not None
                else "An image source could not be read. It was not sent to the model or saved in the image catalog."
            )
            result["status"] = "unavailable"
            part = TextPart(text="[Image unavailable]")
        if temporary:
            part.mark_as_temp()
        self.cached_parts[cache_key] = part
        self.capture_results[cache_key] = result
        return part

    def project_for_hook(self, req) -> None:
        """Expose standard message parts while retaining server-owned identities.

        Args:
            req: Mutable request passed to the existing plugin hook.
        """
        self._hook_parts.clear()
        self._hook_checkpoints.clear()
        self._hook_legacy_remaining.clear()
        contexts = []
        for message in req.contexts:
            if message.get("role") == "_checkpoint":
                if contexts:
                    self._hook_checkpoints.setdefault(id(contexts[-1]), []).append(
                        message
                    )
                continue
            projected = {**message}
            if isinstance(message.get("content"), list):
                parts = []
                for part in message["content"]:
                    if isinstance(part, ImageURLPart):
                        part = part.model_dump_for_context()
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        snapshot = copy.deepcopy(part)
                        self._hook_legacy_remaining.append(snapshot)
                    if isinstance(part, dict) and part.get("type") == "image_ref":
                        shown = {
                            "type": "text",
                            "text": ImageRefPart.model_validate(part).to_text(),
                        }
                        self._hook_parts[id(shown)] = (copy.deepcopy(shown), part)
                        parts.append(shown)
                    else:
                        parts.append(part)
                projected["content"] = parts
            contexts.append(projected)
        req.contexts = contexts
        parts = []
        for part in req.extra_user_content_parts:
            if (
                isinstance(part, ImageRefPart)
                or isinstance(part, dict)
                and part.get("type") == "image_ref"
            ):
                reference = (
                    part
                    if isinstance(part, ImageRefPart)
                    else ImageRefPart.model_validate(part)
                )
                shown = TextPart(text=reference.to_text())
                self._hook_parts[id(shown)] = (shown.model_dump_for_context(), part)
                parts.append(shown)
            else:
                parts.append(part)
        req.extra_user_content_parts = parts

    def restore_after_hook(self, req) -> None:
        """Restore only unmodified projection objects, never matching arbitrary text.

        Args:
            req: Hook-mutated request whose deletions and replacements are respected.

        Raises:
            ValueError: A prepared turn was moved to another conversation.
        """
        if req.conversation is None or req.conversation.cid != self.conversation_id:
            raise ValueError("Image request conversation changed after preparation")
        contexts = []
        new_history_images = []
        for message in req.contexts:
            if isinstance(message.get("content"), list):
                parts = []
                for part in message["content"]:
                    image_data = (
                        part.model_dump_for_context()
                        if isinstance(part, ImageURLPart)
                        else part
                    )
                    if (
                        isinstance(image_data, dict)
                        and image_data.get("type") == "image_url"
                    ):
                        # Inline bytes already present before the hook carry no
                        # asset authorization. Preserve copied legacy occurrences
                        # up to their original count, without migrating them here.
                        previous_index = next(
                            (
                                index
                                for index, previous in enumerate(
                                    self._hook_legacy_remaining
                                )
                                if image_data == previous
                            ),
                            None,
                        )
                        if previous_index is not None:
                            self._hook_legacy_remaining.pop(previous_index)
                        else:
                            new_history_images.append(
                                {**image_data, "_no_save": True}
                                if message.get("_no_save")
                                else image_data
                            )
                            continue
                    saved = self._hook_parts.get(id(part))
                    parts.append(saved[1] if saved and part == saved[0] else part)
                message["content"] = (
                    parts if parts else "[Image attached to current request]"
                )
            contexts.append(message)
            contexts.extend(self._hook_checkpoints.get(id(message), []))
        req.contexts = contexts
        parts = []
        for part in req.extra_user_content_parts:
            saved = self._hook_parts.get(id(part))
            value = (
                part.model_dump_for_context() if isinstance(part, ContentPart) else part
            )
            if saved and value == saved[0]:
                parts.append(saved[1])
            elif (
                saved
                and isinstance(part, ContentPart)
                and part._no_save
                and {key: item for key, item in value.items() if key != "_no_save"}
                == saved[0]
            ):
                temporary = TextPart(text=value.get("text", "")).mark_as_temp()
                visual_key = self.part_visual_keys.get(id(saved[1]))
                if visual_key is not None:
                    self.part_visual_keys[id(temporary)] = visual_key
                parts.append(temporary)
            else:
                parts.append(part)
        req.extra_user_content_parts = parts + new_history_images
        self._hook_parts.clear()
        self._hook_checkpoints.clear()
        self._hook_legacy_remaining.clear()
