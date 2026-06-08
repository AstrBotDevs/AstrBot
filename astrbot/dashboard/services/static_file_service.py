from __future__ import annotations


class StaticFileService:
    INDEX_ROUTES = (
        "/",
        "/auth/login",
        "/config",
        "/logs",
        "/extension",
        "/dashboard/default",
        "/alkaid",
        "/alkaid/knowledge-base",
        "/alkaid/long-term-memory",
        "/alkaid/other",
        "/console",
        "/chat",
        "/settings",
        "/platforms",
        "/providers",
        "/about",
        "/extension-marketplace",
        "/conversation",
        "/tool-use",
    )
    NOT_FOUND_MESSAGE = (
        "404 Not found。如果你初次使用打开面板发现 404, 请参考文档: "
        "https://docs.astrbot.app/faq.html。如果你正在测试回调地址可达性，"
        "显示这段文字说明测试成功了。"
    )

    def list_index_routes(self) -> tuple[str, ...]:
        return self.INDEX_ROUTES

    def get_not_found_message(self) -> str:
        return self.NOT_FOUND_MESSAGE
