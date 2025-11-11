from astrbot_sdk.runtime.start_server import amain

import asyncio

if __name__ == "__main__":
    asyncio.run(amain())  # 使用默认端口 8765
