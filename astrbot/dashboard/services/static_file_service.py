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
        "<!doctype html>"
        '<html lang="zh-CN">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>404 · WebUI 文件缺失 / WebUI files are missing</title>"
        "<style>"
        "*{box-sizing:border-box}"
        "body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#f6f7f9;color:#1f2328}"
        "main{width:min(100%,680px);padding:32px;background:#fff;border:1px solid #e5e7eb;"
        "border-radius:16px}"
        ".status{margin:0 0 8px;color:#6b7280;font-size:14px;font-weight:600;"
        "letter-spacing:.08em}"
        "h1{margin:0 0 12px;font-size:28px}"
        "h2{margin:28px 0 10px;font-size:18px}"
        "h3{margin:28px 0 10px;font-size:18px}"
        "p{margin:0 0 20px;color:#4b5563;line-height:1.7}"
        "code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}"
        "code{padding:2px 6px;background:#f3f4f6;border-radius:6px;color:#111827}"
        ".action{display:inline-block;margin-bottom:24px;padding:10px 16px;border-radius:9px;"
        "background:#3c96ca;color:#fff;text-decoration:none;font-weight:600}"
        ".action:hover{background:#327fab}"
        ".action:focus-visible{outline:3px solid rgba(60,150,202,.3);outline-offset:3px}"
        ".english{margin-top:4px;padding-top:28px;border-top:1px solid #e5e7eb}"
        ".english h2{margin:0 0 12px;font-size:24px}"
        ".label{margin-bottom:8px;font-size:14px;font-weight:600;color:#374151}"
        "pre{margin:0;padding:16px;overflow:auto;border:1px solid #e5e7eb;border-radius:10px;"
        "background:#f9fafb;color:#374151;line-height:1.6}"
        ".note{margin:20px 0 0;font-size:14px;color:#6b7280}"
        "</style>"
        "</head>"
        "<body><main>"
        '<p class="status">404 · NOT FOUND</p>'
        "<h1>WebUI 文件缺失</h1>"
        "<p>AstrBot 会在启动时检测并尝试下载 WebUI 文件。看到此页面说明下载失败或文件不完整，"
        "请先尝试重启 AstrBot。</p>"
        "<h2>手动安装</h2>"
        "<p>如果问题仍然存在，请前往 Releases 下载与当前 AstrBot 版本匹配的 "
        "<code>AstrBot-vx.x.x-dashboard.zip</code>，解压后将 "
        "<code>dist</code> 文件夹放入 <code>AstrBot/data/</code>。</p>"
        '<a class="action" href="https://github.com/AstrBotDevs/AstrBot/releases">'
        "前往 Releases 下载</a>"
        '<section class="english" lang="en">'
        "<h2>WebUI files are missing</h2>"
        "<p>AstrBot checks for WebUI files and attempts to download them at startup. "
        "If you see this page, the download failed or the files are incomplete. "
        "Try restarting AstrBot first.</p>"
        "<h3>Manual installation</h3>"
        "<p>If the issue persists, open Releases and download "
        "<code>AstrBot-vx.x.x-dashboard.zip</code> matching your current AstrBot version. "
        "Extract it and place the <code>dist</code> folder under "
        "<code>AstrBot/data/</code>.</p>"
        '<a class="action" href="https://github.com/AstrBotDevs/AstrBot/releases">'
        "Open Releases</a>"
        "</section>"
        '<p class="label">目录结构 / Directory structure</p>'
        "<pre>AstrBot/\n└── data/\n    └── dist/\n        ├── index.html\n"
        "        └── assets/</pre>"
        '<p class="note">正在测试回调地址？看到此页面表示地址可达。<br>'
        '<span lang="en">Testing a callback URL? This page confirms that the URL is '
        "reachable.</span></p>"
        "</main></body></html>"
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
