"""AstrBot 后台运行入口 (System Tray Edition)

与 ``main.py`` 功能完全一致，但额外提供：
1. 适配 ``pythonw.exe`` 运行（无控制台窗口）；
2. 在 Windows 右下角系统托盘显示图标；
3. 托盘菜单提供「打开 WebUI / 退出」操作。

依赖：
    - pystray   (托盘图标)
    - Pillow    (图标加载, AstrBot 已自带)

启动方式（推荐）::

    pythonw.exe main_bg.py

或者带控制台调试::

    python main_bg.py

作者: AstrBot Agent Harness 开发专家
时间: 2026-05-13 22:06 (CST)
"""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import os
import sys
import threading
import webbrowser
from pathlib import Path

# -----------------------------------------------------------------------------
# pythonw 下 stdout/stderr 为 None，loguru / print 写日志时会抛 OSError。
# 必须在 import astrbot 之前把它们重定向到一个真实可写的对象 / 文件。
# -----------------------------------------------------------------------------
_LOG_DIR = Path(__file__).parent / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_BG_LOG_FILE = _LOG_DIR / "astrbot.log"


def _ensure_stdio() -> None:
    """确保 sys.stdout / sys.stderr 可写（pythonw 下二者为 None）。"""
    if sys.stdout is None or sys.stderr is None:
        # 以行缓冲方式打开，方便实时查看
        f = open(_BG_LOG_FILE, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f


_ensure_stdio()

# -----------------------------------------------------------------------------
# 以下区域与 main.py 完全一致（导入 runtime_bootstrap 之后才能 import astrbot）
# -----------------------------------------------------------------------------
import runtime_bootstrap  # noqa: E402

runtime_bootstrap.initialize_runtime_bootstrap()

from astrbot.core import LogBroker, LogManager, db_helper, logger  # noqa: E402
from astrbot.core.config.default import VERSION  # noqa: E402
from astrbot.core.initial_loader import InitialLoader  # noqa: E402
from astrbot.core.utils.astrbot_path import (  # noqa: E402
    get_astrbot_config_path,
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
    get_astrbot_plugin_path,
    get_astrbot_root,
    get_astrbot_site_packages_path,
    get_astrbot_temp_path,
)
from astrbot.core.utils.io import (  # noqa: E402
    download_dashboard,
    get_dashboard_version,
)

# 将父目录添加到 sys.path
sys.path.append(Path(__file__).parent.as_posix())

logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|

"""

# 托盘图标路径（用户指定）
TRAY_ICON_PATH = Path(r"F:\github\Astrbot\docs\public\logo.png")

# 默认 WebUI 地址（AstrBot 默认面板端口为 6185）
DEFAULT_WEBUI_URL = "http://localhost:6185"


# =============================================================================
# 与 main.py 完全相同的核心逻辑
# =============================================================================
def check_env() -> None:
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 10):
        logger.error("请使用 Python3.10+ 运行本项目。")
        sys.exit()

    astrbot_root = get_astrbot_root()
    if astrbot_root not in sys.path:
        sys.path.insert(0, astrbot_root)

    site_packages_path = get_astrbot_site_packages_path()
    if site_packages_path not in sys.path:
        sys.path.append(site_packages_path)

    os.makedirs(get_astrbot_config_path(), exist_ok=True)
    os.makedirs(get_astrbot_plugin_path(), exist_ok=True)
    os.makedirs(get_astrbot_temp_path(), exist_ok=True)
    os.makedirs(get_astrbot_knowledge_base_path(), exist_ok=True)
    os.makedirs(site_packages_path, exist_ok=True)

    # 针对问题 #181 的临时解决方案
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")


async def check_dashboard_files(webui_dir: str | None = None):
    """下载管理面板文件"""
    if webui_dir:
        if os.path.exists(webui_dir):
            logger.info("Using WebUI directory: %s", webui_dir)
            return webui_dir
        logger.warning("WebUI directory not found: %s. Using default.", webui_dir)

    data_dist_path = os.path.join(get_astrbot_data_path(), "dist")
    if os.path.exists(data_dist_path):
        v = await get_dashboard_version()
        if v is not None:
            if v == f"v{VERSION}":
                logger.info("WebUI is up to date.")
            else:
                logger.warning(
                    "WebUI version mismatch: %s, expected v%s.",
                    v,
                    VERSION,
                )
        return data_dist_path

    logger.info(
        "Downloading WebUI. If it fails, download dist.zip from "
        "https://github.com/AstrBotDevs/AstrBot/releases/latest and "
        "extract dist to data/.",
    )

    try:
        await download_dashboard(version=f"v{VERSION}", latest=False)
    except Exception as e:
        logger.critical(f"下载管理面板文件失败: {e}。")
        return None

    logger.info("管理面板下载完成。")
    return data_dist_path


async def main_async(
    webui_dir_arg: str | None,
    log_broker: "LogBroker",
    stop_event: asyncio.Event,
) -> None:
    """主异步入口

    Parameters
    ----------
    webui_dir_arg : str | None
        WebUI 静态文件目录。
    log_broker : LogBroker
        日志代理。
    stop_event : asyncio.Event
        外部（托盘线程）触发的停止事件。设置后本协程会优雅退出。
    """
    webui_dir = await check_dashboard_files(webui_dir_arg)
    if webui_dir is None:
        logger.warning(
            "管理面板文件检查失败，WebUI 功能将不可用。"
            "请检查网络连接或手动指定 --webui-dir 参数。"
        )

    db = db_helper

    logger.info(logo_tmpl)

    core_lifecycle = InitialLoader(db, log_broker)
    core_lifecycle.webui_dir = webui_dir

    # 将 InitialLoader.start() 包装到 task，并与 stop_event 共同等待
    core_task = asyncio.create_task(core_lifecycle.start(), name="astrbot-core")
    stop_task = asyncio.create_task(stop_event.wait(), name="bg-stop-waiter")

    done, pending = await asyncio.wait(
        {core_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 若是托盘触发退出，则取消核心任务
    if stop_task in done and not core_task.done():
        logger.info("收到托盘退出信号，正在关闭 AstrBot ...")
        core_task.cancel()
        try:
            await core_task
        except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001
            logger.info(f"AstrBot 已停止: {type(e).__name__}")
    else:
        # core 自己结束了
        stop_task.cancel()


# =============================================================================
# 后台 / 托盘相关逻辑
# =============================================================================
class AstrBotBackground:
    """AstrBot 后台运行管理器，负责协调 asyncio loop 与 pystray 托盘。"""

    def __init__(self, webui_dir_arg: str | None) -> None:
        self.webui_dir_arg = webui_dir_arg
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event: asyncio.Event | None = None
        self.core_thread: threading.Thread | None = None
        self.tray_icon = None  # type: ignore[assignment]

    # ---- asyncio 线程 -------------------------------------------------------
    def _run_core(self) -> None:
        """在独立线程中运行 asyncio 事件循环。"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.stop_event = asyncio.Event()

        # 启动日志代理（与 main.py 保持一致）
        log_broker = LogBroker()
        LogManager.set_queue_handler(logger, log_broker)

        try:
            self.loop.run_until_complete(
                main_async(self.webui_dir_arg, log_broker, self.stop_event)
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"AstrBot 后台运行异常: {e}")
        finally:
            try:
                # 清理悬挂任务
                pending = asyncio.all_tasks(self.loop)
                for t in pending:
                    t.cancel()
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                self.loop.close()
            # 核心退出后，确保托盘也退出
            if self.tray_icon is not None:
                try:
                    self.tray_icon.stop()
                except Exception:  # noqa: BLE001
                    pass

    def start_core(self) -> None:
        self.core_thread = threading.Thread(
            target=self._run_core, name="astrbot-core", daemon=True
        )
        self.core_thread.start()

    def request_stop(self) -> None:
        """从托盘线程安全地请求停止 asyncio 循环。"""
        if self.loop is not None and self.stop_event is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)

    # ---- 托盘 ---------------------------------------------------------------
    def _build_tray_icon(self):
        """构建 pystray Icon 对象。"""
        import pystray
        from PIL import Image

        # 加载图标；若找不到则使用纯色占位图
        if TRAY_ICON_PATH.exists():
            image = Image.open(TRAY_ICON_PATH)
        else:
            logger.warning(f"未找到托盘图标 {TRAY_ICON_PATH}，使用占位图。")
            image = Image.new("RGBA", (64, 64), (66, 133, 244, 255))

        def on_open_webui(icon, item):  # noqa: ARG001
            webbrowser.open(DEFAULT_WEBUI_URL)

        def on_open_log(icon, item):  # noqa: ARG001
            try:
                os.startfile(str(_BG_LOG_FILE))  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                webbrowser.open(_BG_LOG_FILE.as_uri())

        def on_quit(icon, item):  # noqa: ARG001
            logger.info("用户从托盘退出 AstrBot")
            self.request_stop()
            # 等待核心线程结束（最多 10 秒），然后停止托盘
            if self.core_thread is not None:
                self.core_thread.join(timeout=10)
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("打开 WebUI", on_open_webui, default=True),
            pystray.MenuItem("打开日志文件", on_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出 AstrBot", on_quit),
        )

        icon = pystray.Icon(
            name="AstrBot",
            icon=image,
            title=f"AstrBot v{VERSION} (后台运行中)",
            menu=menu,
        )
        return icon

    def run(self) -> None:
        # 先启动核心
        self.start_core()
        # 再启动托盘（阻塞主线程，直到 icon.stop() 被调用）
        self.tray_icon = self._build_tray_icon()
        self.tray_icon.run()
        # 托盘退出后，确保核心线程也退出
        self.request_stop()
        if self.core_thread is not None:
            self.core_thread.join(timeout=10)


# =============================================================================
# 入口
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot (Background / Tray Mode)")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="Specify the directory path for WebUI static files",
        default=None,
    )
    args = parser.parse_args()

    check_env()

    try:
        app = AstrBotBackground(args.webui_dir)
        app.run()
    except Exception as e:  # noqa: BLE001
        logger.exception(f"启动 main_bg.py 失败: {e}")
        sys.exit(1)
