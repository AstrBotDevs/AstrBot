import argparse
import asyncio
import sys
from pathlib import Path

from astrbot.__main__ import LogBroker, LogManager, check_env, logger, main_async

# 将父目录添加到 sys.path
sys.path.append(Path(__file__).parent.as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="指定 WebUI 静态文件目录路径",
        default=None,
    )
    args = parser.parse_args()

    check_env()

    # 启动日志代理
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)

    # 只使用一次 asyncio.run()
    asyncio.run(main_async(args.webui_dir))
