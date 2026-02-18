from astrbot.core.utils.runtime_env import is_packaged_electron_runtime

DESKTOP_PACKAGED_UPDATE_BLOCK_MESSAGE = (
    "桌面打包版不支持在线更新。请下载最新安装包并替换当前应用。"
)


def should_block_packaged_update() -> bool:
    return is_packaged_electron_runtime()


def get_packaged_update_block_message() -> str:
    return DESKTOP_PACKAGED_UPDATE_BLOCK_MESSAGE


def ensure_packaged_update_allowed() -> None:
    if should_block_packaged_update():
        raise RuntimeError(get_packaged_update_block_message())
