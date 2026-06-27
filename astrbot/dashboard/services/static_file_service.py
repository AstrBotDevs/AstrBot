from __future__ import annotations

from pathlib import Path


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

    def resolve_index_file(self, static_folder: str | Path | None) -> Path | None:
        if not static_folder:
            return None
        index_file = Path(static_folder) / "index.html"
        if index_file.is_file():
            return index_file
        return None

    def resolve_static_file(
        self,
        static_folder: str | Path | None,
        requested_path: str,
    ) -> Path | None:
        if not static_folder or not requested_path:
            return None
        if requested_path.startswith("api/"):
            return None
        path_parts = requested_path.replace("\\", "/").split("/")
        if requested_path.startswith(("/", "\\")) or ".." in path_parts:
            return None

        static_root = Path(static_folder).resolve()
        target_file = (static_root / requested_path).resolve()
        try:
            target_file.relative_to(static_root)
        except ValueError:
            return None

        if target_file.is_file():
            return target_file
        return None
