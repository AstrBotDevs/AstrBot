"""AstrBot 备份模块共享常量

此文件定义了导出器和导入器共享的常量，确保两端配置一致。
"""

from sqlmodel import SQLModel

from astrbot.core.db.po import (
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationV2,
    Persona,
    PersonaFolder,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
    SessionProjectRelation,
    WebChatThread,
)
from astrbot.core.knowledge_base.models import (
    KBDocument,
    KBMedia,
    KnowledgeBase,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_plugin_data_path,
    get_astrbot_plugin_path,
    get_astrbot_skills_path,
    get_astrbot_t2i_templates_path,
    get_astrbot_temp_path,
    get_astrbot_webchat_path,
)

# ============================================================
# 共享常量 - 确保导出和导入端配置一致
# ============================================================

# 主数据库模型类映射
MAIN_DB_MODELS: dict[str, type[SQLModel]] = {
    "platform_stats": PlatformStat,
    "conversations": ConversationV2,
    "personas": Persona,
    "persona_folders": PersonaFolder,
    "preferences": Preference,
    "platform_message_history": PlatformMessageHistory,
    "platform_sessions": PlatformSession,
    "webchat_threads": WebChatThread,
    "chatui_projects": ChatUIProject,
    "session_project_relations": SessionProjectRelation,
    "attachments": Attachment,
    "command_configs": CommandConfig,
    "command_conflicts": CommandConflict,
}

# 知识库元数据模型类映射
KB_METADATA_MODELS: dict[str, type[SQLModel]] = {
    "knowledge_bases": KnowledgeBase,
    "kb_documents": KBDocument,
    "kb_media": KBMedia,
}


def get_backup_directories() -> dict[str, str]:
    """获取需要备份的目录列表

    使用 astrbot_path 模块动态获取路径，支持通过环境变量 ASTRBOT_ROOT 自定义根目录。

    Returns:
        dict: 键为备份文件中的目录名称，值为目录的绝对路径
    """
    return {
        "plugins": get_astrbot_plugin_path(),  # 插件本体
        "plugin_data": get_astrbot_plugin_data_path(),  # 插件数据
        "config": get_astrbot_config_path(),  # 配置目录
        "t2i_templates": get_astrbot_t2i_templates_path(),  # T2I 模板
        "webchat": get_astrbot_webchat_path(),  # Legacy images within attachments.
        "temp": get_astrbot_temp_path(),  # 临时文件
        "skills": get_astrbot_skills_path(),  # Skills
    }


# 备份清单版本号
# 1.2: additive — adds "components" and "component_checksums" fields and extends
# checksums to every archive entry. Older importers ignore unknown fields, and
# directory import requires >= 1.1, so 1.2 backups remain readable by old versions.
BACKUP_MANIFEST_VERSION = "1.2"

# Non-directory backup components that can be selected individually.
SPECIAL_COMPONENTS: list[str] = [
    "database",
    "knowledge_base",
    "cmd_config",
    "attachments",
]

# Components whose verification failure aborts the whole import before any
# modification. All other components are soft-fail: corrupted entries are
# skipped with warnings and the rest of the import continues.
HARD_FAIL_COMPONENTS: frozenset[str] = frozenset(
    {"database", "knowledge_base", "cmd_config"}
)

# Fixed archive entries that must exist for a declared component to be usable.
# Components not listed here are validated by prefix scan (see _component_has_entries).
_REQUIRED_ENTRIES: dict[str, tuple[str, ...]] = {
    "database": ("databases/main_db.json",),
    "knowledge_base": ("databases/kb_metadata.json",),
    "cmd_config": ("config/cmd_config.json",),
}


def get_backup_components() -> list[str]:
    """Return selectable component ids, including legacy images under attachments.

    Returns:
        Special components followed by independently selectable data directories.
    """
    return SPECIAL_COMPONENTS + [
        name for name in get_backup_directories() if name != "webchat"
    ]


def component_of_entry(name: str) -> str | None:
    """Map an archive entry path to its owning backup component id.

    Args:
        name: Entry path inside the backup ZIP (e.g. "directories/plugins/x.py").

    Returns:
        The component id, or None for entries not owned by any component
        (e.g. "manifest.json" or unknown paths).
    """
    if name == "databases/main_db.json":
        return "database"
    if name == "config/cmd_config.json":
        return "cmd_config"
    if name.startswith("databases/kb_") or name.startswith("files/kb_media/"):
        return "knowledge_base"
    if name.startswith(("files/attachments/", "directories/webchat/imgs/")):
        return "attachments"
    if name.startswith("directories/"):
        parts = name.split("/")
        if (
            len(parts) >= 3
            and parts[1] != "webchat"
            and parts[1] in get_backup_directories()
        ):
            return parts[1]
    return None


def _component_has_entries(component: str, names: set[str], manifest: dict) -> bool:
    """Check whether a component has its required entries in the archive."""
    required = _REQUIRED_ENTRIES.get(component)
    if required is not None:
        return all(entry in names for entry in required)
    if component == "attachments":
        prefixes = ("files/attachments/",)
        if "webchat" in manifest.get("directories", []):
            prefixes += ("directories/webchat/imgs/",)
        return any(n.startswith(prefixes) and not n.endswith("/") for n in names)
    # Directory component: declared in the manifest and has at least one entry.
    return component in manifest.get("directories", []) and any(
        n.startswith(f"directories/{component}/") for n in names
    )


def derive_component_states(
    manifest: dict, namelist: list[str]
) -> tuple[list[str], list[str]]:
    """Derive (available, broken) components from the manifest and real entries.

    Derivation trusts actual ZIP entries, never self-reported manifest booleans.

    - Manifests with a "components" field (v1.2+): a declared component is
      available when its required entries exist, otherwise it is broken
      (declared but corrupted — callers must not silently drop it).
    - Legacy manifests (no "components" field): the exporter always attempted
      a full backup, so every known component is probed against the actual
      entries; there is no "declared" concept and nothing is broken.

    Args:
        manifest: Parsed manifest.json content.
        namelist: Entry names of the backup ZIP.

    Returns:
        A (available, broken) tuple of component id lists.
    """
    names = set(namelist)
    known = get_backup_components()
    declared = manifest.get("components")

    if declared is None:
        available = [
            comp for comp in known if _component_has_entries(comp, names, manifest)
        ]
        return available, []

    available: list[str] = []
    broken: list[str] = []
    for comp in declared:
        if comp not in known:
            continue
        if _component_has_entries(comp, names, manifest):
            available.append(comp)
        else:
            broken.append(comp)
    return available, broken
