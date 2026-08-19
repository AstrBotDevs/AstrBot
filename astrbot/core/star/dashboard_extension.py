"""Dashboard Extension Protocol v1 manifest, SDK, and registry primitives."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import mimetypes
import re
import secrets
import stat
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from .base import Star
    from .star import StarMetadata

logger = logging.getLogger("astrbot")

DASHBOARD_EXTENSION_PROTOCOL_VERSION = 1
DASHBOARD_EXTENSION_DRAIN_TIMEOUT_SECONDS = 10.0
DASHBOARD_EXTENSION_LISTENER_TIMEOUT_SECONDS = 2.0

ALL_OPEN_API_SCOPES = (
    "bot",
    "provider",
    "persona",
    "im",
    "config",
    "chat",
    "kb",
    "memory",
    "data",
    "file",
    "plugin",
    "mcp",
    "skill",
)

PAGE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
ACTION_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
EXTENSION_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MAX_PAGE_ASSET_BYTES = 16 * 1024 * 1024
MAX_PAGE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_PAGE_ASSET_FILES = 256
MAX_PAGE_STYLES = 8
MAX_PAGE_ACTIONS = 64

ALLOWED_PAGE_ASSET_SUFFIXES = frozenset(
    {
        ".js",
        ".mjs",
        ".css",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
    }
)

_ALLOWED_METADATA_FIELDS = frozenset(
    {
        "name",
        "display_name",
        "author",
        "version",
        "desc",
        "short_desc",
        "repo",
        "astrbot_version",
        "support_platforms",
        "requires",
        "dashboard",
        "authorization",
    }
)


class DashboardExtensionError(ValueError):
    """Raised when a Dashboard extension contract is invalid."""


class DashboardRegistrationError(DashboardExtensionError):
    """Raised when a Dashboard registration transaction is invalid."""


class DashboardActionError(Exception):
    """A plugin-declared error whose message is safe to return to the user."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


class DashboardCancellation(Protocol):
    @property
    def cancelled(self) -> bool: ...

    async def wait(self) -> None: ...


@dataclass(frozen=True)
class DashboardActionContext:
    request_id: str
    username: str
    scopes: frozenset[str]
    extension_id: str
    plugin_name: str
    cancellation: DashboardCancellation


@dataclass(frozen=True)
class DashboardFile:
    relative_path: Path
    filename: str | None = None
    content_type: str | None = None

    def __post_init__(self) -> None:
        path_text = str(self.relative_path)
        if (
            self.relative_path.is_absolute()
            or PureWindowsPath(path_text).drive
            or not path_text
            or "\x00" in path_text
            or "\\" in path_text
            or ":" in path_text
            or any(part in {"", ".", ".."} for part in self.relative_path.parts)
        ):
            raise DashboardExtensionError(
                "DashboardFile.relative_path must be a safe relative path"
            )


class DashboardUploadedFile(Protocol):
    filename: str
    content_type: str
    size: int

    def iter_chunks(
        self,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]: ...


def _validate_action_id(value: str) -> str:
    if len(value) > 64 or not ACTION_ID_RE.fullmatch(value):
        raise DashboardExtensionError(f"Invalid Dashboard Action ID: {value!r}")
    return value


def _validate_model_type(model: type[BaseModel], *, field_name: str) -> None:
    if not inspect.isclass(model) or not issubclass(model, BaseModel):
        raise DashboardExtensionError(f"{field_name} must be a Pydantic BaseModel")


def _validate_input_model(model: type[BaseModel], *, field_name: str) -> None:
    _validate_model_type(model, field_name=field_name)
    if model.model_config.get("extra") != "forbid":
        raise DashboardExtensionError(f"{field_name} must set extra='forbid'")


def _validate_action_common(
    *,
    name: str,
    required_scope: str,
    timeout_seconds: int,
    description: str,
) -> None:
    _validate_action_id(name)
    if required_scope not in ALL_OPEN_API_SCOPES:
        raise DashboardExtensionError(
            f"Unknown Dashboard Action scope: {required_scope!r}"
        )
    if not 5 <= timeout_seconds <= 120:
        raise DashboardExtensionError("timeout_seconds must be between 5 and 120")
    if len(description) > 200:
        raise DashboardExtensionError("description must not exceed 200 characters")


def _validate_content_types(content_types: frozenset[str]) -> None:
    for content_type in content_types:
        if (
            not content_type
            or content_type != content_type.lower()
            or "/" not in content_type
            or "*" in content_type
            or ";" in content_type
        ):
            raise DashboardExtensionError(
                f"Invalid allowed content type: {content_type!r}"
            )


def _validate_extensions(extensions: frozenset[str]) -> None:
    for extension in extensions:
        if (
            len(extension) < 2
            or not extension.startswith(".")
            or extension != extension.lower()
            or not extension[1:].isalnum()
        ):
            raise DashboardExtensionError(
                f"Invalid allowed file extension: {extension!r}"
            )


@dataclass(frozen=True)
class DashboardJsonAction:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    required_scope: str = "plugin"
    timeout_seconds: int = 30
    description: str = ""

    def __post_init__(self) -> None:
        _validate_action_common(
            name=self.name,
            required_scope=self.required_scope,
            timeout_seconds=self.timeout_seconds,
            description=self.description,
        )
        _validate_input_model(self.input_model, field_name="input_model")
        _validate_model_type(self.output_model, field_name="output_model")


@dataclass(frozen=True)
class DashboardUploadAction:
    name: str
    fields_model: type[BaseModel]
    output_model: type[BaseModel]
    required_scope: str = "plugin"
    timeout_seconds: int = 30
    description: str = ""
    max_file_bytes: int = 16 * 1024 * 1024
    allowed_content_types: frozenset[str] = frozenset()
    allowed_extensions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_action_common(
            name=self.name,
            required_scope=self.required_scope,
            timeout_seconds=self.timeout_seconds,
            description=self.description,
        )
        _validate_input_model(self.fields_model, field_name="fields_model")
        _validate_model_type(self.output_model, field_name="output_model")
        if not 1 <= self.max_file_bytes <= 64 * 1024 * 1024:
            raise DashboardExtensionError(
                "max_file_bytes must be between 1 byte and 64 MiB"
            )
        _validate_content_types(self.allowed_content_types)
        _validate_extensions(self.allowed_extensions)


@dataclass(frozen=True)
class DashboardFileAction:
    name: str
    input_model: type[BaseModel]
    required_scope: str = "plugin"
    timeout_seconds: int = 30
    description: str = ""
    disposition: Literal["inline", "attachment"] = "inline"
    max_file_bytes: int = 32 * 1024 * 1024
    allowed_content_types: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_action_common(
            name=self.name,
            required_scope=self.required_scope,
            timeout_seconds=self.timeout_seconds,
            description=self.description,
        )
        _validate_input_model(self.input_model, field_name="input_model")
        host_limit = (
            32 * 1024 * 1024 if self.disposition == "inline" else 128 * 1024 * 1024
        )
        if not 1 <= self.max_file_bytes <= host_limit:
            raise DashboardExtensionError(
                f"max_file_bytes must be between 1 byte and {host_limit} bytes"
            )
        _validate_content_types(self.allowed_content_types)


DashboardActionSpec = DashboardJsonAction | DashboardUploadAction | DashboardFileAction
DashboardJsonHandler = Callable[
    [BaseModel, DashboardActionContext],
    Awaitable[BaseModel],
]
DashboardUploadHandler = Callable[
    [DashboardUploadedFile, BaseModel, DashboardActionContext],
    Awaitable[BaseModel],
]
DashboardFileHandler = Callable[
    [BaseModel, DashboardActionContext],
    Awaitable[DashboardFile],
]
DashboardActionHandler = (
    DashboardJsonHandler | DashboardUploadHandler | DashboardFileHandler
)


class _RequiresDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dashboard_extension: Literal[1]


class _PageDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    module: str
    assets_manifest: str
    styles: list[str] = Field(default_factory=list, max_length=MAX_PAGE_STYLES)
    icon: str | None = None
    actions: list[str] = Field(default_factory=list, max_length=MAX_PAGE_ACTIONS)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not PAGE_ID_RE.fullmatch(value):
            raise ValueError("invalid Page ID")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not 1 <= len(value) <= 80:
            raise ValueError("title must contain 1-80 characters")
        return value

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate Page Action ID")
        for value in values:
            _validate_action_id(value)
        return values


class _DashboardDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension_id: str
    pages: list[_PageDeclaration] = Field(min_length=1)

    @field_validator("extension_id")
    @classmethod
    def validate_extension_id(cls, value: str) -> str:
        validate_extension_id(value)
        return value


class _AssetFileDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    size: int = Field(ge=0, le=MAX_PAGE_ASSET_BYTES)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class _AssetsManifestDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    files: list[_AssetFileDeclaration] = Field(
        min_length=1,
        max_length=MAX_PAGE_ASSET_FILES,
    )


@dataclass(frozen=True)
class DashboardPageAsset:
    path: str
    resolved_path: Path
    sha256: str
    size: int
    content_type: str


@dataclass(frozen=True)
class DashboardPageManifest:
    id: str
    title: str
    module: str
    assets_manifest: str
    styles: tuple[str, ...]
    icon: str | None
    actions: tuple[str, ...]
    assets: Mapping[str, DashboardPageAsset]


@dataclass(frozen=True)
class DashboardExtensionManifest:
    extension_id: str
    pages: tuple[DashboardPageManifest, ...]


def validate_extension_id(extension_id: str) -> None:
    if (
        not 3 <= len(extension_id) <= 128
        or extension_id != extension_id.lower()
        or not extension_id.isascii()
    ):
        raise DashboardExtensionError(
            f"Invalid dashboard.extension_id: {extension_id!r}"
        )
    labels = extension_id.split(".")
    if len(labels) < 2 or any(
        not EXTENSION_LABEL_RE.fullmatch(label) for label in labels
    ):
        raise DashboardExtensionError(
            f"Invalid dashboard.extension_id: {extension_id!r}"
        )


def _path_collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _validate_relative_file(
    plugin_root: Path,
    raw_path: str,
    *,
    expected_suffixes: frozenset[str] | None = None,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        raise DashboardExtensionError("Dashboard asset path must be non-empty")
    if "\\" in raw_path:
        raise DashboardExtensionError(f"Backslashes are not allowed: {raw_path!r}")
    if unquote(raw_path) != raw_path or unquote(unquote(raw_path)) != raw_path:
        raise DashboardExtensionError(
            f"Encoded asset paths are not allowed: {raw_path!r}"
        )

    windows_path = PureWindowsPath(raw_path)
    if (
        windows_path.is_absolute()
        or windows_path.drive
        or raw_path.startswith(("/", "//"))
    ):
        raise DashboardExtensionError(
            f"Absolute asset path is not allowed: {raw_path!r}"
        )

    parts = raw_path.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.startswith(".")
        or part.endswith((".", " "))
        or ":" in part
        for part in parts
    ):
        raise DashboardExtensionError(f"Invalid asset path segment: {raw_path!r}")

    try:
        root = plugin_root.resolve(strict=True)
        candidate = (root / Path(*parts)).resolve(strict=True)
    except OSError as exc:
        raise DashboardExtensionError(
            f"Dashboard asset does not exist: {raw_path!r}"
        ) from exc
    if not candidate.is_relative_to(root):
        raise DashboardExtensionError(f"Asset path escapes plugin root: {raw_path!r}")
    try:
        mode = candidate.stat().st_mode
    except OSError as exc:
        raise DashboardExtensionError(f"Unable to stat asset: {raw_path!r}") from exc
    if not stat.S_ISREG(mode):
        raise DashboardExtensionError(f"Asset is not a regular file: {raw_path!r}")
    if (
        expected_suffixes is not None
        and candidate.suffix.lower() not in expected_suffixes
    ):
        raise DashboardExtensionError(f"Asset type is not allowed: {raw_path!r}")
    return candidate


def _read_assets_manifest(
    plugin_root: Path,
    manifest_path: str,
) -> tuple[_AssetsManifestDeclaration, Path]:
    resolved_manifest = _validate_relative_file(
        plugin_root,
        manifest_path,
        expected_suffixes=frozenset({".json"}),
    )
    if resolved_manifest.stat().st_size > 1024 * 1024:
        raise DashboardExtensionError("assets_manifest exceeds 1 MiB")
    try:
        raw = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        declaration = _AssetsManifestDeclaration.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise DashboardExtensionError(
            f"Invalid assets_manifest: {manifest_path!r}"
        ) from exc
    return declaration, resolved_manifest


def _hash_open_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(128 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _build_page_manifest(
    plugin_root: Path,
    page: _PageDeclaration,
) -> DashboardPageManifest:
    _validate_relative_file(
        plugin_root,
        page.module,
        expected_suffixes=frozenset({".js", ".mjs"}),
    )
    for style in page.styles:
        _validate_relative_file(
            plugin_root,
            style,
            expected_suffixes=frozenset({".css"}),
        )
    declaration, _resolved_manifest = _read_assets_manifest(
        plugin_root,
        page.assets_manifest,
    )
    assets: dict[str, DashboardPageAsset] = {}
    collision_keys: dict[str, str] = {}
    total_bytes = 0
    for file_entry in declaration.files:
        collision_key = _path_collision_key(file_entry.path)
        previous_path = collision_keys.get(collision_key)
        if previous_path is not None:
            raise DashboardExtensionError(
                f"Asset path collision: {previous_path!r} and {file_entry.path!r}"
            )
        collision_keys[collision_key] = file_entry.path
        resolved = _validate_relative_file(
            plugin_root,
            file_entry.path,
            expected_suffixes=ALLOWED_PAGE_ASSET_SUFFIXES,
        )
        actual_size, actual_digest = _hash_open_file(resolved)
        if actual_size != file_entry.size or actual_digest != file_entry.sha256:
            raise DashboardExtensionError(
                f"Asset size or digest mismatch: {file_entry.path!r}"
            )
        total_bytes += actual_size
        if total_bytes > MAX_PAGE_TOTAL_BYTES:
            raise DashboardExtensionError("Page assets exceed the 32 MiB total limit")
        content_type = mimetypes.guess_type(resolved.name)[0]
        if content_type is None:
            raise DashboardExtensionError(
                f"Unable to derive asset content type: {file_entry.path!r}"
            )
        assets[file_entry.path] = DashboardPageAsset(
            path=file_entry.path,
            resolved_path=resolved,
            sha256=file_entry.sha256,
            size=file_entry.size,
            content_type=content_type,
        )

    required_assets = {page.module, *page.styles}
    missing_assets = sorted(required_assets.difference(assets))
    if missing_assets:
        raise DashboardExtensionError(
            f"module/styles missing from assets_manifest: {missing_assets}"
        )
    if Path(page.module).suffix.lower() not in {".js", ".mjs"}:
        raise DashboardExtensionError("Dashboard Page module must be .js or .mjs")
    if any(Path(style).suffix.lower() != ".css" for style in page.styles):
        raise DashboardExtensionError("Dashboard Page styles must be .css files")
    if len(page.styles) != len(set(page.styles)):
        raise DashboardExtensionError("Dashboard Page styles contain duplicates")

    return DashboardPageManifest(
        id=page.id,
        title=page.title,
        module=page.module,
        assets_manifest=page.assets_manifest,
        styles=tuple(page.styles),
        icon=page.icon,
        actions=tuple(page.actions),
        assets=MappingProxyType(assets),
    )


def validate_dashboard_manifest(
    metadata: Mapping[str, Any],
    plugin_root: Path,
) -> DashboardExtensionManifest | None:
    """Validate the strict Dashboard v1 section of plugin metadata."""
    if "pages" in metadata:
        raise DashboardExtensionError(
            "top-level pages is unsupported; use dashboard.pages"
        )
    unknown_fields = sorted(set(metadata).difference(_ALLOWED_METADATA_FIELDS))
    if unknown_fields:
        raise DashboardExtensionError(
            f"Unknown metadata fields: {', '.join(unknown_fields)}"
        )

    dashboard_raw = metadata.get("dashboard")
    requires_raw = metadata.get("requires")
    if dashboard_raw is None:
        if requires_raw is not None:
            try:
                _RequiresDeclaration.model_validate(requires_raw)
            except ValidationError as exc:
                raise DashboardExtensionError("Invalid requires section") from exc
            raise DashboardExtensionError(
                "requires.dashboard_extension needs a dashboard section"
            )
        return None
    if requires_raw is None:
        raise DashboardExtensionError(
            "Dashboard extensions must declare requires.dashboard_extension: 1"
        )

    try:
        _RequiresDeclaration.model_validate(requires_raw)
        dashboard = _DashboardDeclaration.model_validate(dashboard_raw)
    except ValidationError as exc:
        raise DashboardExtensionError("Invalid Dashboard extension metadata") from exc

    page_ids: set[str] = set()
    pages: list[DashboardPageManifest] = []
    for page in dashboard.pages:
        if page.id in page_ids:
            raise DashboardExtensionError(f"Duplicate Dashboard Page ID: {page.id}")
        page_ids.add(page.id)
        pages.append(_build_page_manifest(plugin_root, page))
    return DashboardExtensionManifest(
        extension_id=dashboard.extension_id,
        pages=tuple(pages),
    )


class DashboardActionKind(StrEnum):
    JSON = "json"
    UPLOAD = "upload"
    FILE = "file"


class DashboardExtensionState(StrEnum):
    DISCOVERED = "discovered"
    VALIDATING = "validating"
    REGISTERING = "registering"
    ACTIVE = "active"
    DRAINING = "draining"
    INACTIVE = "inactive"


class DashboardLifecycleEventKind(StrEnum):
    GENERATION_ACTIVATING = "generation_activating"
    DRAINING = "draining"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class DashboardRegisteredAction:
    id: str
    kind: DashboardActionKind
    spec: DashboardActionSpec
    handler: DashboardActionHandler
    owner: Star
    generation: str


@dataclass(frozen=True)
class DashboardExtensionSnapshot:
    extension_id: str
    plugin_name: str
    plugin_root: Path
    owner_key: tuple[bool, str]
    generation: str
    pages: tuple[DashboardPageManifest, ...]
    actions: Mapping[str, DashboardRegisteredAction]


@dataclass(frozen=True)
class DashboardExtensionLifecycleEvent:
    kind: DashboardLifecycleEventKind
    extension_id: str
    plugin_name: str
    generation: str
    reason: str


@dataclass
class _RegistrationTransaction:
    metadata: StarMetadata
    owner: Star
    owner_key: tuple[bool, str]
    generation: str
    manifest: DashboardExtensionManifest | None
    actions: dict[str, DashboardRegisteredAction] = field(default_factory=dict)
    open: bool = True


@dataclass
class _GenerationRecord:
    snapshot: DashboardExtensionSnapshot
    state: DashboardExtensionState
    inflight: set[asyncio.Task[Any]] = field(default_factory=set)


DashboardLifecycleListener = Callable[
    [DashboardExtensionLifecycleEvent],
    Awaitable[None] | None,
]


class DashboardExtensionRegistrar:
    """Owner-bound registrar valid only during one initialize transaction."""

    def __init__(
        self,
        registry: DashboardExtensionRegistry,
        owner: Star,
        generation: str,
    ) -> None:
        self._registry = registry
        self._owner = owner
        self._generation = generation

    def register_json(
        self,
        action: DashboardJsonAction,
        handler: DashboardJsonHandler,
    ) -> None:
        self._registry._register_action(
            self._owner,
            self._generation,
            DashboardActionKind.JSON,
            action,
            handler,
        )

    def register_upload(
        self,
        action: DashboardUploadAction,
        handler: DashboardUploadHandler,
    ) -> None:
        self._registry._register_action(
            self._owner,
            self._generation,
            DashboardActionKind.UPLOAD,
            action,
            handler,
        )

    def register_file(
        self,
        action: DashboardFileAction,
        handler: DashboardFileHandler,
    ) -> None:
        self._registry._register_action(
            self._owner,
            self._generation,
            DashboardActionKind.FILE,
            action,
            handler,
        )


class DashboardExtensionAccess:
    """Context-owned entry point that binds registration to a managed Star."""

    def __init__(self, registry: DashboardExtensionRegistry) -> None:
        self._registry = registry

    def for_plugin(self, plugin: Star) -> DashboardExtensionRegistrar:
        return self._registry.registrar_for(plugin)


class DashboardExtensionRegistry:
    """Atomic registry for Dashboard extension manifests and Action generations."""

    def __init__(self) -> None:
        self._staging_by_owner: dict[int, _RegistrationTransaction] = {}
        self._records_by_extension: dict[str, _GenerationRecord] = {}
        self._extension_by_owner_key: dict[tuple[bool, str], str] = {}
        self._listeners: set[DashboardLifecycleListener] = set()

    @staticmethod
    def _owner_key(metadata: StarMetadata) -> tuple[bool, str]:
        if not metadata.root_dir_name:
            raise DashboardRegistrationError("Plugin root_dir_name is not available")
        return metadata.reserved, metadata.root_dir_name

    def begin_registration(
        self,
        metadata: StarMetadata,
        owner: Star,
    ) -> str:
        if metadata.star_cls is not owner:
            raise DashboardRegistrationError("Registrar owner does not match metadata")
        owner_id = id(owner)
        if owner_id in self._staging_by_owner:
            raise DashboardRegistrationError("Plugin is already registering")
        owner_key = self._owner_key(metadata)
        manifest = metadata.dashboard
        if manifest is not None:
            existing = self._records_by_extension.get(manifest.extension_id)
            if existing is not None and existing.snapshot.owner_key != owner_key:
                raise DashboardRegistrationError(
                    f"Dashboard extension ID is already owned: {manifest.extension_id}"
                )
            if (
                existing is not None
                and existing.snapshot.owner_key == owner_key
                and existing.state is not DashboardExtensionState.INACTIVE
            ):
                raise DashboardRegistrationError(
                    "Dashboard extension generation is still active: "
                    f"{manifest.extension_id}"
                )
            for transaction in self._staging_by_owner.values():
                if (
                    transaction.manifest is not None
                    and transaction.manifest.extension_id == manifest.extension_id
                    and transaction.owner_key != owner_key
                ):
                    raise DashboardRegistrationError(
                        f"Dashboard extension ID is already registering: {manifest.extension_id}"
                    )

        generation = secrets.token_urlsafe(24)
        self._staging_by_owner[owner_id] = _RegistrationTransaction(
            metadata=metadata,
            owner=owner,
            owner_key=owner_key,
            generation=generation,
            manifest=manifest,
        )
        return generation

    def registrar_for(self, owner: Star) -> DashboardExtensionRegistrar:
        transaction = self._staging_by_owner.get(id(owner))
        if (
            transaction is None
            or not transaction.open
            or transaction.owner is not owner
            or transaction.metadata.star_cls is not owner
        ):
            raise DashboardRegistrationError(
                "Dashboard Actions can only be registered during initialize()"
            )
        return DashboardExtensionRegistrar(self, owner, transaction.generation)

    def _register_action(
        self,
        owner: Star,
        generation: str,
        kind: DashboardActionKind,
        spec: DashboardActionSpec,
        handler: DashboardActionHandler,
    ) -> None:
        transaction = self._staging_by_owner.get(id(owner))
        if (
            transaction is None
            or not transaction.open
            or transaction.owner is not owner
            or transaction.generation != generation
            or transaction.metadata.star_cls is not owner
        ):
            raise DashboardRegistrationError("Stale or foreign Dashboard registrar")
        if transaction.manifest is None:
            raise DashboardRegistrationError(
                "Plugin must declare dashboard metadata before registering Actions"
            )
        if not callable(handler):
            raise DashboardRegistrationError("Dashboard Action handler is not callable")
        expected_spec_type: type[DashboardActionSpec]
        expected_parameters: int
        if kind is DashboardActionKind.JSON:
            expected_spec_type = DashboardJsonAction
            expected_parameters = 2
        elif kind is DashboardActionKind.UPLOAD:
            expected_spec_type = DashboardUploadAction
            expected_parameters = 3
        else:
            expected_spec_type = DashboardFileAction
            expected_parameters = 2
        if not isinstance(spec, expected_spec_type):
            raise DashboardRegistrationError("Dashboard Action kind/spec mismatch")
        if not inspect.iscoroutinefunction(handler):
            raise DashboardRegistrationError("Dashboard Action handler must be async")
        try:
            inspect.signature(handler).bind(*([object()] * expected_parameters))
        except TypeError as exc:
            raise DashboardRegistrationError(
                "Dashboard Action handler has an invalid signature"
            ) from exc
        if spec.name in transaction.actions:
            raise DashboardRegistrationError(
                f"Duplicate Dashboard Action ID: {spec.name}"
            )
        transaction.actions[spec.name] = DashboardRegisteredAction(
            id=spec.name,
            kind=kind,
            spec=spec,
            handler=handler,
            owner=owner,
            generation=generation,
        )

    async def commit_registration(
        self, owner: Star
    ) -> DashboardExtensionSnapshot | None:
        transaction = self._staging_by_owner.get(id(owner))
        if (
            transaction is None
            or not transaction.open
            or transaction.owner is not owner
        ):
            raise DashboardRegistrationError("No open Dashboard registration")
        transaction.open = False
        try:
            if transaction.manifest is None:
                if transaction.actions:
                    raise DashboardRegistrationError(
                        "Actions were registered without Dashboard metadata"
                    )
                return None

            registered_actions = set(transaction.actions)
            for page in transaction.manifest.pages:
                missing = sorted(set(page.actions).difference(registered_actions))
                if missing:
                    raise DashboardRegistrationError(
                        f"Page {page.id!r} references unregistered Actions: {missing}"
                    )

            extension_id = transaction.manifest.extension_id
            existing = self._records_by_extension.get(extension_id)
            if (
                existing is not None
                and existing.snapshot.owner_key != transaction.owner_key
            ):
                raise DashboardRegistrationError(
                    f"Dashboard extension ID is already owned: {extension_id}"
                )
            if (
                existing is not None
                and existing.snapshot.owner_key == transaction.owner_key
                and existing.state is not DashboardExtensionState.INACTIVE
            ):
                raise DashboardRegistrationError(
                    f"Dashboard extension generation is still active: {extension_id}"
                )
            plugin_name = transaction.metadata.name or "unknown"
            plugin_root = self._plugin_root(transaction.metadata)
            snapshot = DashboardExtensionSnapshot(
                extension_id=extension_id,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                owner_key=transaction.owner_key,
                generation=transaction.generation,
                pages=transaction.manifest.pages,
                actions=MappingProxyType(dict(transaction.actions)),
            )
            self._records_by_extension[extension_id] = _GenerationRecord(
                snapshot=snapshot,
                state=DashboardExtensionState.ACTIVE,
            )
            self._extension_by_owner_key[transaction.owner_key] = extension_id
            await self._publish(
                DashboardExtensionLifecycleEvent(
                    kind=DashboardLifecycleEventKind.GENERATION_ACTIVATING,
                    extension_id=extension_id,
                    plugin_name=plugin_name,
                    generation=transaction.generation,
                    reason="registration_committed",
                )
            )
            return snapshot
        finally:
            self._staging_by_owner.pop(id(owner), None)

    def rollback_registration(self, owner: Star) -> None:
        transaction = self._staging_by_owner.pop(id(owner), None)
        if transaction is not None:
            transaction.open = False

    def rollback_metadata(self, metadata: StarMetadata) -> None:
        for owner_id, transaction in list(self._staging_by_owner.items()):
            if transaction.metadata is metadata:
                transaction.open = False
                self._staging_by_owner.pop(owner_id, None)

    def validate_staged_generation(
        self,
        staging: DashboardExtensionRegistry,
        current: StarMetadata,
        replacement: StarMetadata,
    ) -> None:
        """Validate a staged replacement without draining the live generation."""
        try:
            replacement_owner_key = self._owner_key(replacement)
        except DashboardRegistrationError:
            return

        staged_extension_id = staging._extension_by_owner_key.get(
            replacement_owner_key,
        )
        if staged_extension_id is None:
            return
        staged_record = staging._records_by_extension.get(staged_extension_id)
        if (
            staged_record is None
            or staged_record.state is not DashboardExtensionState.ACTIVE
            or staged_record.snapshot.owner_key != replacement_owner_key
        ):
            raise DashboardRegistrationError(
                "Staged Dashboard extension generation is not active",
            )
        existing = self._records_by_extension.get(staged_extension_id)
        if (
            existing is not None
            and existing.snapshot.owner_key != replacement_owner_key
        ):
            raise DashboardRegistrationError(
                f"Dashboard extension ID is already owned: {staged_extension_id}",
            )

    async def promote_staged_generation(
        self,
        staging: DashboardExtensionRegistry,
        current: StarMetadata,
        replacement: StarMetadata,
        *,
        reason: str,
    ) -> None:
        """Replace one live extension generation with an isolated staged one.

        A replacement plugin is initialized against ``staging`` while the
        currently active generation remains reachable.  Only after that
        initialization has completed can its action generation be moved into
        this live registry.  A failed staged initialization therefore cannot
        drain or overwrite the live Dashboard extension.

        Args:
            staging: Isolated registry used by the replacement generation.
            current: Currently active plugin metadata.
            replacement: Fully initialized replacement metadata.
            reason: Lifecycle reason used for the retiring generation.

        Raises:
            DashboardRegistrationError: If the staged generation is invalid
                for this live registry.
        """
        self.validate_staged_generation(staging, current, replacement)
        try:
            replacement_owner_key = self._owner_key(replacement)
        except DashboardRegistrationError:
            replacement_owner_key = None
        staged_extension_id = (
            staging._extension_by_owner_key.get(replacement_owner_key)
            if replacement_owner_key is not None
            else None
        )
        staged_record = (
            staging._records_by_extension.get(staged_extension_id)
            if staged_extension_id is not None
            else None
        )

        await self.deactivate(current, reason=reason, release=True)

        if staged_record is None or staged_extension_id is None:
            return
        assert replacement_owner_key is not None

        staging._records_by_extension.pop(staged_extension_id, None)
        staging._extension_by_owner_key.pop(replacement_owner_key, None)
        self._records_by_extension[staged_extension_id] = staged_record
        self._extension_by_owner_key[replacement_owner_key] = staged_extension_id
        await self._publish(
            DashboardExtensionLifecycleEvent(
                kind=DashboardLifecycleEventKind.GENERATION_ACTIVATING,
                extension_id=staged_extension_id,
                plugin_name=staged_record.snapshot.plugin_name,
                generation=staged_record.snapshot.generation,
                reason="staged_generation_promoted",
            ),
        )

    @staticmethod
    def _plugin_root(metadata: StarMetadata) -> Path:
        dashboard_root = getattr(metadata, "dashboard_root", None)
        if not isinstance(dashboard_root, Path):
            raise DashboardRegistrationError("Validated plugin root is unavailable")
        return dashboard_root

    def get_snapshot(self, extension_id: str) -> DashboardExtensionSnapshot | None:
        record = self._records_by_extension.get(extension_id)
        if record is None or record.state is not DashboardExtensionState.ACTIVE:
            return None
        return record.snapshot

    def get_record(
        self,
        extension_id: str,
    ) -> tuple[DashboardExtensionState, DashboardExtensionSnapshot] | None:
        record = self._records_by_extension.get(extension_id)
        if record is None:
            return None
        return record.state, record.snapshot

    def snapshots(self) -> tuple[DashboardExtensionSnapshot, ...]:
        return tuple(
            record.snapshot
            for record in self._records_by_extension.values()
            if record.state is DashboardExtensionState.ACTIVE
        )

    def subscribe(self, listener: DashboardLifecycleListener) -> Callable[[], None]:
        self._listeners.add(listener)

        def unsubscribe() -> None:
            self._listeners.discard(listener)

        return unsubscribe

    async def _publish(self, event: DashboardExtensionLifecycleEvent) -> None:
        for listener in tuple(self._listeners):
            try:
                result = listener(event)
                if inspect.isawaitable(result):
                    await asyncio.wait_for(
                        result,
                        timeout=DASHBOARD_EXTENSION_LISTENER_TIMEOUT_SECONDS,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Dashboard extension lifecycle listener failed for %s/%s",
                    event.extension_id,
                    event.kind,
                    exc_info=True,
                )

    def register_inflight(
        self,
        extension_id: str,
        generation: str,
        task: asyncio.Task[Any],
    ) -> None:
        record = self._records_by_extension.get(extension_id)
        if (
            record is None
            or record.state is not DashboardExtensionState.ACTIVE
            or record.snapshot.generation != generation
        ):
            raise DashboardRegistrationError("Dashboard generation is not active")
        record.inflight.add(task)

    def unregister_inflight(
        self,
        extension_id: str,
        generation: str,
        task: asyncio.Task[Any],
    ) -> None:
        record = self._records_by_extension.get(extension_id)
        if record is not None and record.snapshot.generation == generation:
            record.inflight.discard(task)

    async def deactivate(
        self,
        metadata: StarMetadata,
        *,
        reason: str,
        release: bool = False,
    ) -> None:
        self.rollback_metadata(metadata)
        try:
            owner_key = self._owner_key(metadata)
        except DashboardRegistrationError:
            return
        extension_id = self._extension_by_owner_key.get(owner_key)
        if extension_id is None:
            return
        record = self._records_by_extension.get(extension_id)
        if record is None or record.snapshot.owner_key != owner_key:
            return
        if record.state is DashboardExtensionState.INACTIVE:
            if release:
                self._records_by_extension.pop(extension_id, None)
                self._extension_by_owner_key.pop(owner_key, None)
            return
        if record.state is DashboardExtensionState.ACTIVE:
            record.state = DashboardExtensionState.DRAINING
            await self._publish(
                DashboardExtensionLifecycleEvent(
                    kind=DashboardLifecycleEventKind.DRAINING,
                    extension_id=extension_id,
                    plugin_name=record.snapshot.plugin_name,
                    generation=record.snapshot.generation,
                    reason=reason,
                )
            )

        tasks = {task for task in record.inflight if not task.done()}
        if tasks:
            _done, pending = await asyncio.wait(
                tasks,
                timeout=DASHBOARD_EXTENSION_DRAIN_TIMEOUT_SECONDS,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        record.inflight.clear()
        record.state = DashboardExtensionState.INACTIVE
        await self._publish(
            DashboardExtensionLifecycleEvent(
                kind=DashboardLifecycleEventKind.INACTIVE,
                extension_id=extension_id,
                plugin_name=record.snapshot.plugin_name,
                generation=record.snapshot.generation,
                reason=reason,
            )
        )
        if release:
            self._records_by_extension.pop(extension_id, None)
            self._extension_by_owner_key.pop(owner_key, None)
