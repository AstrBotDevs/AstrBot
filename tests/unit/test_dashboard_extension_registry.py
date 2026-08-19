import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

import astrbot.core.star.dashboard_extension as dashboard_extension
from astrbot.core.star.dashboard_extension import (
    ACTION_ID_RE,
    DashboardActionKind,
    DashboardExtensionAccess,
    DashboardExtensionError,
    DashboardExtensionRegistry,
    DashboardExtensionState,
    DashboardFile,
    DashboardFileAction,
    DashboardJsonAction,
    DashboardLifecycleEventKind,
    DashboardRegistrationError,
    DashboardUploadAction,
    validate_dashboard_manifest,
)
from astrbot.core.star.plugin_runtime_loader import PluginRuntimeLoader
from astrbot.core.star.star import StarMetadata

MALICIOUS_FIXTURE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "plugins" / "dashboard_extension_malicious"
)
EXAMPLE_FIXTURE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "plugins" / "dashboard_extension_example"
)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResultModel(BaseModel):
    ok: bool


class UploadFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str


class PermissiveRequest(BaseModel):
    value: str | None = None


async def json_handler(_payload, _context):
    return ResultModel(ok=True)


async def upload_handler(_file, _fields, _context):
    return ResultModel(ok=True)


async def file_handler(_payload, _context):
    return DashboardFile(Path("result.webp"), content_type="image/webp")


def test_example_fixture_declares_dashboard_v1_capability_and_loads():
    metadata = PluginRuntimeLoader.load_metadata(str(EXAMPLE_FIXTURE_ROOT))

    assert metadata.dashboard is not None
    assert metadata.dashboard.extension_id == (
        "team.xero.astrbot-dashboard-extension-example"
    )
    assert metadata.dashboard.pages[0].id == "settings"
    assert metadata.dashboard.pages[0].actions == ("settings.read",)


def test_dashboard_plugin_metadata_accepts_authorization_actions(tmp_path: Path):
    plugin_root = tmp_path / "dashboard_extension_example"
    shutil.copytree(EXAMPLE_FIXTURE_ROOT, plugin_root)
    metadata_path = plugin_root / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    metadata["authorization"] = {"actions": [{"id": "settings.read"}]}
    metadata_path.write_text(
        yaml.safe_dump(metadata, sort_keys=False),
        encoding="utf-8",
    )

    loaded = PluginRuntimeLoader.load_metadata(str(plugin_root))

    assert loaded.authorization_actions == frozenset(
        {"plugin:xero-team/dashboard_extension_example:settings.read"}
    )


@pytest.mark.parametrize("capability", [None, 2])
def test_metadata_loader_requires_exact_dashboard_v1_capability(
    tmp_path: Path,
    capability: int | None,
):
    plugin_root = tmp_path / "dashboard_extension_example"
    shutil.copytree(EXAMPLE_FIXTURE_ROOT, plugin_root)
    metadata_path = plugin_root / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    if capability is None:
        metadata.pop("requires")
    else:
        metadata["requires"]["dashboard_extension"] = capability
    metadata_path.write_text(
        yaml.safe_dump(metadata, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(DashboardExtensionError):
        PluginRuntimeLoader.load_metadata(str(plugin_root))


def _write_file(root: Path, relative_path: str, content: bytes) -> dict:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _page_declaration(
    root: Path,
    *,
    page_id: str = "settings",
    actions: list[str] | None = None,
    manifest_name: str | None = None,
) -> dict:
    manifest_name = manifest_name or f"pages/{page_id}/assets.v1.json"
    module_path = f"pages/{page_id}/app.js"
    style_path = f"pages/{page_id}/style.css"
    chunk_path = f"pages/{page_id}/chunks/vendor-a1b2c3.js"
    files = [
        _write_file(root, module_path, b"import './chunks/vendor-a1b2c3.js';\n"),
        _write_file(root, style_path, b"body { color: black; }\n"),
        _write_file(root, chunk_path, b"export const value = 1;\n"),
    ]
    manifest_path = root / manifest_name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"version": 1, "files": files}),
        encoding="utf-8",
    )
    return {
        "id": page_id,
        "title": page_id.title(),
        "module": module_path,
        "assets_manifest": manifest_name,
        "styles": [style_path],
        "icon": "mdi-palette",
        "actions": actions or ["config.read"],
    }


def _metadata_document(
    root: Path,
    *,
    extension_id: str = "io.github.example.palette",
    pages: list[dict] | None = None,
) -> dict:
    return {
        "name": "astrbot_plugin_palette",
        "display_name": "Palette",
        "author": "Example",
        "version": "1.0.0",
        "desc": "Dashboard extension test plugin",
        "astrbot_version": ">=4.27",
        "requires": {"dashboard_extension": 1},
        "dashboard": {
            "extension_id": extension_id,
            "pages": pages or [_page_declaration(root)],
        },
    }


def _validated_manifest(
    root: Path,
    *,
    extension_id: str = "io.github.example.palette",
    pages: list[dict] | None = None,
):
    return validate_dashboard_manifest(
        _metadata_document(root, extension_id=extension_id, pages=pages),
        root,
    )


def _metadata(
    root: Path,
    owner: object,
    *,
    extension_id: str = "io.github.example.palette",
    root_dir_name: str = "astrbot_plugin_palette",
    plugin_name: str = "astrbot_plugin_palette",
    actions: list[str] | None = None,
) -> StarMetadata:
    manifest = _validated_manifest(
        root,
        extension_id=extension_id,
        pages=[_page_declaration(root, actions=actions)],
    )
    return StarMetadata(
        name=plugin_name,
        root_dir_name=root_dir_name,
        star_cls=owner,  # type: ignore[arg-type]
        dashboard=manifest,
        dashboard_root=root.resolve(),
    )


def _json_action(name: str = "config.read") -> DashboardJsonAction:
    return DashboardJsonAction(
        name=name,
        input_model=EmptyRequest,
        output_model=ResultModel,
    )


def test_valid_manifest_supports_single_and_multiple_pages(tmp_path: Path):
    first = _page_declaration(tmp_path, page_id="settings")
    second = _page_declaration(tmp_path, page_id="preview")

    manifest = _validated_manifest(tmp_path, pages=[first, second])

    assert manifest is not None
    assert manifest.extension_id == "io.github.example.palette"
    assert [page.id for page in manifest.pages] == ["settings", "preview"]
    assert set(manifest.pages[0].assets) == {
        "pages/settings/app.js",
        "pages/settings/style.css",
        "pages/settings/chunks/vendor-a1b2c3.js",
    }


def test_malicious_fixture_plugin_is_rejected_before_registration():
    with pytest.raises(DashboardExtensionError):
        PluginRuntimeLoader.load_metadata(str(MALICIOUS_FIXTURE_ROOT))


@pytest.mark.parametrize(
    "extension_id",
    [
        "ab",
        "SINGLE.label",
        "single",
        "io..palette",
        "io.github.example.-palette",
        "io.github.example.palette-",
        f"io.{'a' * 64}",
        f"io.github.{'a' * 120}",
    ],
)
def test_manifest_rejects_invalid_extension_ids(
    tmp_path: Path,
    extension_id: str,
):
    with pytest.raises(DashboardExtensionError):
        _validated_manifest(tmp_path, extension_id=extension_id)


@pytest.mark.parametrize(
    "page_id",
    ["", "Settings", "1settings", "settings_page", "a" * 49],
)
def test_manifest_rejects_invalid_page_ids(tmp_path: Path, page_id: str):
    page = _page_declaration(tmp_path)
    page["id"] = page_id

    with pytest.raises(DashboardExtensionError):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_duplicate_page_ids(tmp_path: Path):
    first = _page_declaration(tmp_path, page_id="settings")
    second = dict(first)

    with pytest.raises(DashboardExtensionError, match="Duplicate Dashboard Page ID"):
        _validated_manifest(tmp_path, pages=[first, second])


@pytest.mark.parametrize(
    "action_id",
    ["", "Config.read", "1config", "config..read", "config/read", "a" * 65],
)
def test_manifest_rejects_invalid_action_ids(tmp_path: Path, action_id: str):
    page = _page_declaration(tmp_path, actions=[action_id])

    with pytest.raises(DashboardExtensionError):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_duplicate_action_ids(tmp_path: Path):
    page = _page_declaration(
        tmp_path,
        actions=["config.read", "config.read"],
    )

    with pytest.raises(DashboardExtensionError):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_top_level_pages_and_unknown_fields(tmp_path: Path):
    metadata = _metadata_document(tmp_path)
    metadata["pages"] = []
    with pytest.raises(DashboardExtensionError, match="top-level pages"):
        validate_dashboard_manifest(metadata, tmp_path)

    metadata = _metadata_document(tmp_path)
    metadata["dashbord"] = metadata["dashboard"]
    with pytest.raises(DashboardExtensionError, match="Unknown metadata fields"):
        validate_dashboard_manifest(metadata, tmp_path)


def test_manifest_rejects_unknown_or_missing_protocol_version(tmp_path: Path):
    metadata = _metadata_document(tmp_path)
    metadata["requires"]["dashboard_extension"] = 2
    with pytest.raises(DashboardExtensionError):
        validate_dashboard_manifest(metadata, tmp_path)

    metadata = _metadata_document(tmp_path)
    del metadata["requires"]
    with pytest.raises(DashboardExtensionError, match="requires.dashboard_extension"):
        validate_dashboard_manifest(metadata, tmp_path)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/app.js",
        "C:/Windows/app.js",
        "//server/share/app.js",
        "../app.js",
        "pages\\settings\\app.js",
        "pages//app.js",
        "pages/./app.js",
        "pages/%2e%2e/app.js",
        "pages/%252e%252e/app.js",
        "pages/app.js:stream",
        "pages/app.js.",
        "pages/app.js ",
        "pages/app\x00.js",
        "pages/.secret.js",
    ],
)
def test_manifest_rejects_malicious_module_paths(tmp_path: Path, bad_path: str):
    page = _page_declaration(tmp_path)
    page["module"] = bad_path

    with pytest.raises(DashboardExtensionError):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.js"
    outside.write_text("export default 1;", encoding="utf-8")
    link = tmp_path / "pages" / "settings" / "escape.js"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    page = _page_declaration(tmp_path)
    page["module"] = "pages/settings/escape.js"
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = outside.read_bytes()
    assets["files"].append(
        {
            "path": page["module"],
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
    )
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="escapes plugin root"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_missing_module_and_style_entries(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"] = [
        item for item in assets["files"] if item["path"] != page["module"]
    ]
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="module/styles missing"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_declared_asset_that_does_not_exist(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"][0]["path"] = "pages/settings/missing.js"
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="does not exist"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_asset_directory(tmp_path: Path):
    page = _page_declaration(tmp_path)
    directory_path = tmp_path / "pages/settings/directory.js"
    directory_path.mkdir()
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"].append(
        {
            "path": "pages/settings/directory.js",
            "sha256": "0" * 64,
            "size": 0,
        }
    )
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="not a regular file"):
        _validated_manifest(tmp_path, pages=[page])


@pytest.mark.parametrize("field", ["size", "sha256"])
def test_manifest_rejects_asset_size_and_digest_mismatch(
    tmp_path: Path,
    field: str,
):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"][0][field] = 1 if field == "size" else "0" * 64
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="size or digest mismatch"):
        _validated_manifest(tmp_path, pages=[page])


@pytest.mark.parametrize("suffix", [".py", ".svg", ".wasm", ".map"])
def test_manifest_rejects_disallowed_asset_types(tmp_path: Path, suffix: str):
    page = _page_declaration(tmp_path)
    relative = f"pages/settings/blocked{suffix}"
    entry = _write_file(tmp_path, relative, b"blocked")
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"].append(entry)
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="type is not allowed"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_unknown_assets_manifest_fields(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["content_type"] = "application/javascript"
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="Invalid assets_manifest"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_unknown_assets_manifest_version(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["version"] = 2
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="Invalid assets_manifest"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_more_than_256_assets(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets["files"].extend([assets["files"][0]] * 254)
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="Invalid assets_manifest"):
        _validated_manifest(tmp_path, pages=[page])


def test_manifest_rejects_page_assets_over_32_mib(tmp_path: Path):
    page = _page_declaration(tmp_path)
    manifest_path = tmp_path / page["assets_manifest"]
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    large_content = b"x" * (16 * 1024 * 1024)
    assets["files"].append(
        _write_file(tmp_path, "pages/settings/large-one.png", large_content)
    )
    assets["files"].append(
        _write_file(tmp_path, "pages/settings/large-two.png", large_content)
    )
    manifest_path.write_text(json.dumps(assets), encoding="utf-8")

    with pytest.raises(DashboardExtensionError, match="32 MiB"):
        _validated_manifest(tmp_path, pages=[page])


def test_path_collision_key_covers_case_and_unicode_normalization():
    assert dashboard_extension._path_collision_key(  # noqa: SLF001
        "pages/Caf\N{LATIN SMALL LETTER E WITH ACUTE}.js"
    ) == dashboard_extension._path_collision_key(  # noqa: SLF001
        "PAGES/CAFE\N{COMBINING ACUTE ACCENT}.JS"
    )


def test_action_specs_enforce_ids_scopes_models_and_limits():
    assert ACTION_ID_RE.fullmatch("config.read")
    with pytest.raises(DashboardExtensionError):
        DashboardJsonAction(
            name="Config.read",
            input_model=EmptyRequest,
            output_model=ResultModel,
        )
    with pytest.raises(DashboardExtensionError, match="extra='forbid'"):
        DashboardJsonAction(
            name="config.read",
            input_model=PermissiveRequest,
            output_model=ResultModel,
        )
    with pytest.raises(DashboardExtensionError, match="Unknown.*scope"):
        DashboardJsonAction(
            name="config.read",
            input_model=EmptyRequest,
            output_model=ResultModel,
            required_scope="owner",
        )
    with pytest.raises(DashboardExtensionError):
        DashboardUploadAction(
            name="background.upload",
            fields_model=UploadFields,
            output_model=ResultModel,
            max_file_bytes=65 * 1024 * 1024,
        )
    with pytest.raises(DashboardExtensionError):
        DashboardFileAction(
            name="background.thumbnail",
            input_model=EmptyRequest,
            disposition="inline",
            max_file_bytes=33 * 1024 * 1024,
        )


def test_dashboard_file_rejects_absolute_and_traversal_paths(tmp_path: Path):
    with pytest.raises(DashboardExtensionError):
        DashboardFile(tmp_path / "absolute.webp")
    with pytest.raises(DashboardExtensionError):
        DashboardFile(Path("../outside.webp"))


@pytest.mark.asyncio
async def test_registration_is_staged_and_committed_atomically(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    access = DashboardExtensionAccess(registry)
    owner = object()
    metadata = _metadata(tmp_path, owner)

    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    access.for_plugin(owner).register_json(  # type: ignore[arg-type]
        _json_action(),
        json_handler,
    )
    assert registry.snapshots() == ()

    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]

    assert snapshot is not None
    assert registry.get_snapshot(snapshot.extension_id) is snapshot
    assert snapshot.actions["config.read"].kind is DashboardActionKind.JSON


@pytest.mark.asyncio
async def test_registration_failure_leaves_no_partial_snapshot(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(
        tmp_path,
        owner,
        actions=["config.read", "config.write"],
    )
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
        _json_action(),
        json_handler,
    )

    with pytest.raises(DashboardRegistrationError, match="unregistered Actions"):
        await registry.commit_registration(owner)  # type: ignore[arg-type]

    assert registry.snapshots() == ()
    with pytest.raises(DashboardRegistrationError):
        registry.registrar_for(owner)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_promote_staged_generation_keeps_live_extension_until_commit(
    tmp_path: Path,
):
    """A staged replacement cannot affect the live extension before promotion."""
    live_registry = DashboardExtensionRegistry()
    current_owner = object()
    current_root = tmp_path / "current"
    current_root.mkdir()
    current = _metadata(
        current_root,
        current_owner,
        root_dir_name="reloadable_plugin",
    )
    live_registry.begin_registration(current, current_owner)  # type: ignore[arg-type]
    live_registry.registrar_for(current_owner).register_json(  # type: ignore[arg-type]
        _json_action(),
        json_handler,
    )
    current_snapshot = await live_registry.commit_registration(current_owner)  # type: ignore[arg-type]
    assert current_snapshot is not None

    staging_registry = DashboardExtensionRegistry()
    replacement_owner = object()
    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir()
    replacement = _metadata(
        replacement_root,
        replacement_owner,
        root_dir_name="reloadable_plugin",
    )
    staging_registry.begin_registration(replacement, replacement_owner)  # type: ignore[arg-type]
    staging_registry.registrar_for(replacement_owner).register_json(  # type: ignore[arg-type]
        _json_action(),
        json_handler,
    )
    replacement_snapshot = await staging_registry.commit_registration(  # type: ignore[arg-type]
        replacement_owner,
    )
    assert replacement_snapshot is not None

    assert live_registry.get_snapshot(current_snapshot.extension_id) is current_snapshot

    await live_registry.promote_staged_generation(
        staging_registry,
        current,
        replacement,
        reason="reload",
    )

    assert (
        live_registry.get_snapshot(replacement_snapshot.extension_id)
        is replacement_snapshot
    )
    assert staging_registry.snapshots() == ()


def test_registration_rejects_constructor_foreign_stale_and_duplicate_owners(
    tmp_path: Path,
):
    registry = DashboardExtensionRegistry()
    access = DashboardExtensionAccess(registry)
    owner = object()
    foreign = object()
    metadata = _metadata(tmp_path, owner)

    with pytest.raises(DashboardRegistrationError, match="during initialize"):
        access.for_plugin(owner)  # type: ignore[arg-type]
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    with pytest.raises(DashboardRegistrationError):
        access.for_plugin(foreign)  # type: ignore[arg-type]
    registrar = access.for_plugin(owner)  # type: ignore[arg-type]
    registrar.register_json(_json_action(), json_handler)
    with pytest.raises(DashboardRegistrationError, match="Duplicate"):
        registrar.register_json(_json_action(), json_handler)


def test_registration_rejects_actions_without_dashboard_manifest(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = StarMetadata(
        name="plain_plugin",
        root_dir_name="plain_plugin",
        star_cls=owner,  # type: ignore[arg-type]
        dashboard_root=tmp_path.resolve(),
    )
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]

    with pytest.raises(DashboardRegistrationError, match="declare dashboard"):
        registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
            _json_action(),
            json_handler,
        )


def test_registration_rejects_kind_and_handler_signature_mismatch(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(tmp_path, owner)
    generation = registry.begin_registration(metadata, owner)  # type: ignore[arg-type]

    async def wrong_handler(_payload):
        return ResultModel(ok=True)

    with pytest.raises(DashboardRegistrationError, match="kind/spec mismatch"):
        registry._register_action(  # noqa: SLF001
            owner,  # type: ignore[arg-type]
            generation,
            DashboardActionKind.FILE,
            _json_action(),
            file_handler,
        )
    with pytest.raises(DashboardRegistrationError, match="invalid signature"):
        registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
            _json_action(),
            wrong_handler,
        )


@pytest.mark.asyncio
async def test_extension_id_collision_blocks_other_install_but_allows_rename(
    tmp_path: Path,
):
    registry = DashboardExtensionRegistry()
    first_owner = object()
    first_root = tmp_path / "first"
    first_root.mkdir()
    first = _metadata(first_root, first_owner, root_dir_name="first")
    registry.begin_registration(first, first_owner)  # type: ignore[arg-type]
    registry.registrar_for(first_owner).register_json(  # type: ignore[arg-type]
        _json_action(), json_handler
    )
    first_snapshot = await registry.commit_registration(first_owner)  # type: ignore[arg-type]
    assert first_snapshot is not None

    other_owner = object()
    other_root = tmp_path / "other"
    other_root.mkdir()
    other = _metadata(other_root, other_owner, root_dir_name="other")
    with pytest.raises(DashboardRegistrationError, match="already owned"):
        registry.begin_registration(other, other_owner)  # type: ignore[arg-type]

    await registry.deactivate(first, reason="reload")
    renamed_owner = object()
    renamed = _metadata(
        first_root,
        renamed_owner,
        root_dir_name="first",
        plugin_name="renamed_palette",
    )
    registry.begin_registration(renamed, renamed_owner)  # type: ignore[arg-type]
    registry.registrar_for(renamed_owner).register_json(  # type: ignore[arg-type]
        _json_action(), json_handler
    )
    renamed_snapshot = await registry.commit_registration(renamed_owner)  # type: ignore[arg-type]

    assert renamed_snapshot is not None
    assert renamed_snapshot.plugin_name == "renamed_palette"
    assert renamed_snapshot.generation != first_snapshot.generation


@pytest.mark.asyncio
async def test_old_registrar_and_generation_cannot_override_new_generation(
    tmp_path: Path,
):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(tmp_path, owner)
    generation = registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registrar = registry.registrar_for(owner)  # type: ignore[arg-type]
    registrar.register_json(_json_action(), json_handler)
    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]
    assert snapshot is not None

    with pytest.raises(DashboardRegistrationError):
        registrar.register_json(
            DashboardJsonAction(
                name="config.write",
                input_model=EmptyRequest,
                output_model=ResultModel,
            ),
            json_handler,
        )
    with pytest.raises(DashboardRegistrationError):
        registry.register_inflight(
            snapshot.extension_id,
            generation + "-stale",
            asyncio.current_task(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_deactivate_drains_cancels_and_fails_closed_when_listener_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        dashboard_extension,
        "DASHBOARD_EXTENSION_DRAIN_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        dashboard_extension,
        "DASHBOARD_EXTENSION_LISTENER_TIMEOUT_SECONDS",
        0.01,
    )
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(tmp_path, owner)
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
        _json_action(), json_handler
    )
    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]
    assert snapshot is not None
    events = []

    async def failing_listener(event):
        events.append(event.kind)
        raise RuntimeError("listener failed")

    async def hanging_listener(_event):
        await asyncio.Event().wait()

    registry.subscribe(failing_listener)
    registry.subscribe(hanging_listener)
    task = asyncio.create_task(asyncio.Event().wait())
    registry.register_inflight(snapshot.extension_id, snapshot.generation, task)

    await registry.deactivate(metadata, reason="reload")

    record = registry.get_record(snapshot.extension_id)
    assert record is not None
    assert record[0] is DashboardExtensionState.INACTIVE
    assert registry.get_snapshot(snapshot.extension_id) is None
    assert task.cancelled()
    assert DashboardLifecycleEventKind.DRAINING in events
    assert DashboardLifecycleEventKind.INACTIVE in events


@pytest.mark.asyncio
async def test_release_removes_uninstalled_owner(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(tmp_path, owner)
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
        _json_action(), json_handler
    )
    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]
    assert snapshot is not None

    await registry.deactivate(metadata, reason="uninstall", release=True)

    assert registry.get_record(snapshot.extension_id) is None
    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir()
    replacement_owner = object()
    replacement = _metadata(
        replacement_root,
        replacement_owner,
        root_dir_name="replacement",
    )
    registry.begin_registration(replacement, replacement_owner)  # type: ignore[arg-type]


def test_upload_and_file_registration_shapes(tmp_path: Path):
    registry = DashboardExtensionRegistry()
    owner = object()
    metadata = _metadata(
        tmp_path,
        owner,
        actions=["background.upload", "background.thumbnail"],
    )
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registrar = registry.registrar_for(owner)  # type: ignore[arg-type]
    registrar.register_upload(
        DashboardUploadAction(
            name="background.upload",
            fields_model=UploadFields,
            output_model=ResultModel,
            allowed_content_types=frozenset({"image/png"}),
            allowed_extensions=frozenset({".png"}),
        ),
        upload_handler,
    )
    registrar.register_file(
        DashboardFileAction(
            name="background.thumbnail",
            input_model=EmptyRequest,
            disposition="inline",
            allowed_content_types=frozenset({"image/webp"}),
        ),
        file_handler,
    )
