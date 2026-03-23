from __future__ import annotations

import anyio

from astrbot._internal.abc.base_astrbot_gateway import BaseAstrbotGateway
from astrbot._internal.abc.base_astrbot_orchestrator import BaseAstrbotOrchestrator
from astrbot._internal.geteway.server import AstrbotGateway
from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator


async def bootstrap():
    orchestrator: BaseAstrbotOrchestrator = AstrbotOrchestrator()
    gw: BaseAstrbotGateway = AstrbotGateway(orchestrator)

    # anyio 的结构化并发
    async with anyio.create_task_group() as tg:
        tg.start_soon(orchestrator.lsp.connect)  # 启动 LSP client
        tg.start_soon(orchestrator.mcp.connect)  # 启动 MCP client
        tg.start_soon(orchestrator.acp.connect)  # 启动 ACP client
        tg.start_soon(orchestrator.abp.connect)  # 启动 ABP client
        await anyio.sleep(0.5)
        tg.start_soon(orchestrator.run_loop)  # 启动编排器循环

        tg.start_soon(gw.serve)  # 面板后端服务
