"""AstrBot 备份模块共享常量

此文件定义了导出器和导入器共享的常量，确保两端配置一致。
"""

from sqlmodel import SQLModel

from astrbot.core.db.po import (
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
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
    "image_assets": ImageAsset,
    "conversation_image_checkpoints": ConversationImageCheckpoint,
    "conversation_image_refs": ConversationImageRef,
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
        "webchat": get_astrbot_webchat_path(),  # WebChat 数据
        "temp": get_astrbot_temp_path(),  # 临时文件
        "skills": get_astrbot_skills_path(),  # Skills
    }


# 备份清单版本号
BACKUP_MANIFEST_VERSION = "1.1"

IMAGE_BACKUP_TABLES = (
    "image_assets",
    "conversation_image_checkpoints",
    "conversation_image_refs",
)
IMAGE_MEDIA_PREFIX = "media/image_assets/"


def validate_image_backup_data(data: dict) -> None:
    """Validate the complete image graph before publishing or replacing data.

    Args:
        data: Main database tables represented as JSON-compatible dictionaries.

    Raises:
        ValueError: Metadata, identities, relationships or history references differ.
    """
    import re
    import uuid

    from astrbot.core.agent.message import ImageRefPart, get_checkpoint_id
    from astrbot.core.image_asset_store import DEFAULT_MAX_FILE_BYTES

    assets = {}
    for row in data.get("image_assets", []):
        asset = ImageAsset.model_validate(row)
        if (
            asset.asset_id in assets
            or str(uuid.UUID(asset.asset_id)) != asset.asset_id
            or asset.storage_key != f"{asset.asset_id}.img"
            or not 0 < asset.byte_size <= DEFAULT_MAX_FILE_BYTES
            or re.fullmatch(r"[0-9a-f]{64}", asset.sha256) is None
            or asset.state not in {"available", "unavailable", "pending_delete"}
            or asset.source_kind not in {"original", "legacy_model_input"}
        ):
            raise ValueError("Invalid or duplicate image asset metadata")
        assets[asset.asset_id] = asset
    conversations = {
        row["conversation_id"]: row for row in data.get("conversations", [])
    }
    if len(conversations) != len(data.get("conversations", [])):
        raise ValueError("Duplicate conversation identities in image snapshot")
    checkpoints = {}
    sequences = set()
    for row in data.get("conversation_image_checkpoints", []):
        checkpoint = ConversationImageCheckpoint.model_validate(row)
        key = (checkpoint.conversation_id, checkpoint.checkpoint_id)
        sequence_key = (checkpoint.conversation_id, checkpoint.sequence)
        if (
            checkpoint.conversation_id not in conversations
            or key in checkpoints
            or sequence_key in sequences
            or checkpoint.sequence <= 0
            or not checkpoint.checkpoint_id
            or not isinstance(row.get("active"), bool)
        ):
            raise ValueError("Invalid image checkpoint ledger")
        checkpoints[key] = checkpoint
        sequences.add(sequence_key)
    refs = {}
    for row in data.get("conversation_image_refs", []):
        ref = ConversationImageRef.model_validate(row)
        key = (ref.conversation_id, ref.occurrence_id)
        if (
            key in refs
            or ref.conversation_id not in conversations
            or ref.asset_id not in assets
            or assets[ref.asset_id].state == "pending_delete"
            or ref.description_status not in {"pending", "ready", "failed"}
        ):
            raise ValueError("Invalid image conversation association")
        if ref.checkpoint_id:
            checkpoint = checkpoints.get((ref.conversation_id, ref.checkpoint_id))
            if checkpoint is None or not checkpoint.active:
                raise ValueError("Image association has no active checkpoint")
        refs[key] = ref
    # Legacy text-only editing permits duplicate/reordered checkpoint markers.
    # The database normalizes that ledger before the first image is associated.
    image_conversations = {cid for cid, _ in refs}
    for cid, conversation in conversations.items():
        last_sequence = 0
        pending_refs = []
        for message in conversation.get("content") or []:
            if not isinstance(message, dict):
                continue
            checkpoint_id = get_checkpoint_id(message)
            if checkpoint_id:
                checkpoint = checkpoints.get((cid, checkpoint_id))
                if cid in image_conversations:
                    if (
                        checkpoint is None
                        or not checkpoint.active
                        or checkpoint.sequence <= last_sequence
                    ):
                        raise ValueError("History checkpoint order differs from ledger")
                    last_sequence = checkpoint.sequence
                if any(
                    ref.checkpoint_id and ref.checkpoint_id != checkpoint_id
                    for ref in pending_refs
                ):
                    raise ValueError("History image belongs to another checkpoint")
                pending_refs.clear()
            if not isinstance(message.get("content"), list):
                continue
            for item in message["content"]:
                if isinstance(item, dict) and item.get("type") == "image_ref":
                    part = ImageRefPart.model_validate(item)
                    ref = refs.get((cid, part.occurrence_id))
                    if ref is None or ref.asset_id != part.asset_id:
                        raise ValueError(
                            "History image reference has no matching association"
                        )
                    pending_refs.append(ref)
        if any(ref.checkpoint_id for ref in pending_refs):
            raise ValueError("History image has no closing checkpoint")
