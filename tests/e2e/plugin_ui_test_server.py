"""Minimal HTTP server for Dashboard plugin Page browser transport tests."""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import ssl
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

HOST = "127.0.0.1"
BACKEND_PORT = 6185
SPIKE_PORT = 6190
DASHBOARD_PORT = 3000
TEST_DASHBOARD_TOKEN = "plugin-ui-e2e-dashboard-token"
TEST_DASHBOARD_USER = "plugin-ui-e2e"
TEST_EXTENSION_ID = "io.github.example.palette"
TEST_PLUGIN_NAME = "astrbot_plugin_palette"
TEST_PAGE_ID = "settings"
TEST_GENERATION = "generation-1"
TEST_INSTANCE_ID = "instance-1"
TEST_NONCE = "nonce-1"
TEST_SESSION_PREFIX = "/api/plugin-pages/v1/sessions/host-session/"
TEST_BUNDLE_ID = "a" * 64
TEST_BUNDLE_PREFIX = f"/api/plugin-pages/v1/bundles/{TEST_BUNDLE_ID}/"
TEST_SDK_PATH = "/api/plugin-pages/v1/sdk.e2e-v1.js"
TEST_INLINE_FILE_PATH = "/api/plugin-files/v1/inline-ticket"
TEST_DOWNLOAD_FILE_PATH = "/api/plugin-files/v1/download-ticket"
SESSION_COOKIE = "astrbot_plugin_page=spike-session-secret"
SESSION_PREFIX = "/api/plugin-pages/v1/sessions/spike/"
BUNDLE_PREFIX = "/api/plugin-pages/v1/bundles/spike-bundle/"
SDK_PATH = "/api/plugin-pages/v1/sdk.spike-v1.js"
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FONT_PATH = (
    REPO_ROOT
    / "dashboard"
    / "src"
    / "assets"
    / "fonts"
    / "files"
    / "astrbot-noto-sans-sc-07-regular.woff2"
)

REQUESTS: list[dict[str, object]] = []
REQUESTS_LOCK = threading.Lock()

TEST_PLUGIN = {
    "name": TEST_PLUGIN_NAME,
    "display_name": "Palette",
    "desc": "Dashboard Extension Protocol v1 fixture",
    "version": "1.0.0",
    "activated": True,
    "reserved": False,
    "components": [
        {
            "type": "page",
            "name": TEST_PAGE_ID,
            "title": "Palette Settings",
            "description": "Configure Palette",
            "extension_id": TEST_EXTENSION_ID,
            "page_id": TEST_PAGE_ID,
            "icon": "mdi-palette",
            "plugin_name": TEST_PLUGIN_NAME,
            "plugin_marketplace_name": "astrbot-plugin-palette",
        }
    ],
}

TEST_ACTIONS = [
    {
        "id": "config.read",
        "kind": "json",
        "required_scope": "plugin",
        "description": "Read config",
        "input_schema": {},
        "output_schema": {},
    },
    {
        "id": "config.fail",
        "kind": "json",
        "required_scope": "plugin",
        "description": "Return a public failure",
        "input_schema": {},
        "output_schema": {},
    },
    {
        "id": "background.upload",
        "kind": "upload",
        "required_scope": "plugin",
        "description": "Upload a background",
        "input_schema": {},
        "output_schema": {},
        "max_file_bytes": 1048576,
        "allowed_content_types": ["image/png"],
        "allowed_extensions": [".png"],
    },
    {
        "id": "background.thumbnail",
        "kind": "file",
        "required_scope": "plugin",
        "description": "Read a thumbnail",
        "input_schema": {},
        "disposition": "inline",
    },
    {
        "id": "background.download",
        "kind": "file",
        "required_scope": "plugin",
        "description": "Download a background",
        "input_schema": {},
        "disposition": "attachment",
    },
]

TEST_PAGE_APP_JS = b"""const page = window.AstrBotPluginPage;
const context = await page.ready();
const root = document.querySelector('#astrbot-plugin-root');
root.innerHTML = `
  <h1>Palette Settings</h1>
  <div data-testid="page-context"></div>
  <div data-testid="page-security"></div>
  <div data-testid="action-result"></div>
  <button data-testid="invoke-json">Invoke JSON</button>
  <button data-testid="invoke-error">Invoke Error</button>
  <input data-testid="upload-file" type="file" />
  <button data-testid="preview-file">Preview</button>
  <img data-testid="preview-image" alt="preview" />
  <button data-testid="download-file">Download</button>
  <button data-testid="navigate-external">Navigate</button>
`;
const renderContext = (value) => {
  root.querySelector('[data-testid="page-context"]').textContent =
    `${value.locale}:${value.theme.mode}:${value.plugin_generation}`;
};
renderContext(context);
page.onContext(renderContext);
const security = [];
try { void parent.document.body; security.push('parent-readable'); }
catch { security.push('parent-blocked'); }
try { void localStorage.length; security.push('storage-readable'); }
catch { security.push('storage-blocked'); }
try { security.push(document.cookie ? 'cookie-readable' : 'cookie-empty'); }
catch { security.push('cookie-blocked'); }
try { await fetch('/api/v1/plugins'); security.push('api-readable'); }
catch { security.push('api-blocked'); }
root.querySelector('[data-testid="page-security"]').textContent = security.join(',');
root.querySelector('[data-testid="invoke-json"]').onclick = async () => {
  const result = await page.invoke('config.read', {});
  root.querySelector('[data-testid="action-result"]').textContent = JSON.stringify(result);
};
root.querySelector('[data-testid="invoke-error"]').onclick = async () => {
  try { await page.invoke('config.fail', {}); }
  catch (error) { root.querySelector('[data-testid="action-result"]').textContent = error.code; }
};
root.querySelector('[data-testid="upload-file"]').onchange = async (event) => {
  const result = await page.upload('background.upload', event.target.files[0], {});
  root.querySelector('[data-testid="action-result"]').textContent = JSON.stringify(result);
};
root.querySelector('[data-testid="preview-file"]').onclick = async () => {
  const file = await page.readFile('background.thumbnail', {});
  root.querySelector('[data-testid="preview-image"]').src = page.createObjectURL(file);
  root.querySelector('[data-testid="action-result"]').textContent = file.filename;
};
root.querySelector('[data-testid="download-file"]').onclick = () =>
  page.download('background.download', {});
root.querySelector('[data-testid="navigate-external"]').onclick = () => {
  location.href = 'https://example.com/plugin-page-navigation';
  setTimeout(() => location.reload(), 100);
};
"""


def _test_shell() -> tuple[bytes, str]:
    dashboard_origin = f"http://{HOST}:{DASHBOARD_PORT}"
    asset_source = f"{dashboard_origin}{TEST_BUNDLE_PREFIX}"
    sdk_source = f"{dashboard_origin}{TEST_SDK_PATH}"
    csp = "; ".join(
        (
            "sandbox allow-scripts",
            "default-src 'none'",
            f"script-src {sdk_source} {asset_source}",
            f"style-src {asset_source}",
            f"img-src {asset_source} data: blob:",
            f"font-src {asset_source} data:",
            f"media-src {asset_source} blob:",
            "connect-src 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            "frame-src 'none'",
            "form-action 'none'",
            "navigate-to 'none'",
            "frame-ancestors 'self'",
            "worker-src 'none'",
        )
    )
    html = f"""<!doctype html>
<html>
  <head><meta charset="utf-8" /></head>
  <body>
    <div id="astrbot-plugin-root">loading</div>
    <script src="{TEST_SDK_PATH}"></script>
    <script type="module" src="{TEST_BUNDLE_PREFIX}app.js" crossorigin="anonymous"></script>
  </body>
</html>"""
    return html.encode(), csp


def _shell(port: int) -> tuple[bytes, bytes]:
    origin = f"https://{HOST}:{port}"
    asset_source = f"{origin}{BUNDLE_PREFIX}"
    sdk_source = f"{origin}{SDK_PATH}"
    csp = "; ".join(
        (
            "sandbox allow-scripts",
            "default-src 'none'",
            f"script-src {sdk_source} {asset_source}",
            f"style-src {asset_source}",
            f"img-src {asset_source} data: blob:",
            f"font-src {asset_source} data:",
            f"media-src {asset_source} blob:",
            "connect-src 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            "frame-src 'none'",
            "form-action 'none'",
            "navigate-to 'none'",
            "frame-ancestors 'self'",
            "worker-src 'none'",
        )
    )
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="{BUNDLE_PREFIX}style.css" crossorigin="anonymous" />
  </head>
  <body>
    <div id="astrbot-plugin-root">transport spike</div>
    <script src="{SDK_PATH}"></script>
    <script type="module" src="{BUNDLE_PREFIX}app.js" crossorigin="anonymous"></script>
  </body>
</html>"""
    return html.encode(), csp.encode()


HOST_HTML = b"""<!doctype html>
<html>
  <body>
    <div data-testid="spike-status">loading</div>
    <iframe
      data-testid="plugin-frame"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      allow=""
      src="/api/plugin-pages/v1/sessions/spike/"
    ></iframe>
    <script>
      window.spikeMessages = [];
      const expected = new Set([
        'sdk-loaded',
        'module-loaded',
        'static-import-loaded',
        'dynamic-import-loaded',
        'css-loaded',
        'image-loaded',
        'font-loaded',
      ]);
      window.addEventListener('message', (event) => {
        if (typeof event.data !== 'string' || !expected.has(event.data)) return;
        window.spikeMessages.push(event.data);
        if ([...expected].every((item) => window.spikeMessages.includes(item))) {
          document.querySelector('[data-testid="spike-status"]').textContent = 'complete';
        }
      });
    </script>
  </body>
</html>"""

SDK_JS = b"window.parent.postMessage('sdk-loaded', '*');\n"
STATIC_JS = (
    b"window.parent.postMessage('static-import-loaded', '*'); export const value = 1;\n"
)
DYNAMIC_JS = b"window.parent.postMessage('dynamic-import-loaded', '*'); export const value = 2;\n"
APP_JS = b"""import './static.js';
window.parent.postMessage('module-loaded', '*');
await import('./dynamic.js');
const marker = document.createElement('div');
marker.id = 'css-marker';
marker.textContent = 'css';
document.body.append(marker);
if (getComputedStyle(marker).fontFamily.includes('SpikeFont')) {
  window.parent.postMessage('css-loaded', '*');
}
const image = new Image();
image.onload = () => window.parent.postMessage('image-loaded', '*');
image.src = new URL('./pixel.png', import.meta.url).href;
await document.fonts.load('16px SpikeFont');
window.parent.postMessage('font-loaded', '*');
"""
STYLE_CSS = b"""@font-face {
  font-family: 'SpikeFont';
  src: url('./font.woff2') format('woff2');
}
#css-marker {
  font-family: 'SpikeFont';
  background-image: url('./pixel.png');
}
"""


class SpikeHandler(BaseHTTPRequestHandler):
    server_version = "AstrBotPluginUISpike/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(
        self,
        body: bytes,
        *,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        data: object,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._send(
            json.dumps(data).encode(),
            content_type="application/json; charset=utf-8",
            status=status,
            headers=headers,
        )

    def _authorized(self) -> bool:
        return (
            self.headers.get("Authorization") == f"Bearer {TEST_DASHBOARD_TOKEN}"
            and f"astrbot_dashboard_jwt={TEST_DASHBOARD_TOKEN}"
            in self.headers.get("Cookie", "")
        )

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        self._send_json(
            {"status": "error", "message": "Unauthorized", "data": None},
            status=HTTPStatus.UNAUTHORIZED,
            headers={"Cache-Control": "no-store"},
        )
        return False

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        value = json.loads(self.rfile.read(length))
        return value if isinstance(value, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(b"ok", content_type="text/plain")
            return
        if self.server.server_port == BACKEND_PORT:
            if path in {
                "/api/v1/chat/projects",
                "/api/v1/chat/sessions",
                "/api/v1/providers/type/chat_completion",
            }:
                if not self._require_authorized():
                    return
                self._send_json({"status": "ok", "message": None, "data": []})
                return
            if path == "/api/v1/commands":
                if not self._require_authorized():
                    return
                self._send_json(
                    {
                        "status": "ok",
                        "message": None,
                        "data": {"items": [], "wake_prefix": ["/"]},
                    }
                )
                return
            if path == "/api/v1/plugins":
                if not self._require_authorized():
                    return
                self._send_json(
                    {"status": "ok", "message": None, "data": [TEST_PLUGIN]}
                )
                return
            if path == "/api/v1/plugins/failed":
                if not self._require_authorized():
                    return
                self._send_json({"status": "ok", "message": None, "data": {}})
                return
            if path == "/api/v1/plugins/sources":
                if not self._require_authorized():
                    return
                self._send_json({"status": "ok", "message": None, "data": []})
                return
            if path == f"/api/v1/plugins/{TEST_PLUGIN_NAME}":
                if not self._require_authorized():
                    return
                self._send_json({"status": "ok", "message": None, "data": TEST_PLUGIN})
                return
            if path == f"/api/v1/plugins/{TEST_PLUGIN_NAME}/readme":
                if not self._require_authorized():
                    return
                self._send_json(
                    {"status": "ok", "message": None, "data": {"content": ""}}
                )
                return
            if path == f"/api/v1/plugins/{TEST_PLUGIN_NAME}/changelog":
                if not self._require_authorized():
                    return
                self._send_json(
                    {"status": "ok", "message": None, "data": {"content": ""}}
                )
                return
            if path == f"/api/v1/plugins/{TEST_EXTENSION_ID}/dashboard":
                if not self._require_authorized():
                    return
                self._send_json(
                    {
                        "status": "ok",
                        "message": None,
                        "data": {
                            "protocol_version": 1,
                            "extension_id": TEST_EXTENSION_ID,
                            "plugin_name": TEST_PLUGIN_NAME,
                            "plugin_generation": TEST_GENERATION,
                            "pages": [
                                {
                                    "id": TEST_PAGE_ID,
                                    "title": "Palette Settings",
                                    "icon": "mdi-palette",
                                    "actions": [
                                        action["id"] for action in TEST_ACTIONS
                                    ],
                                }
                            ],
                            "actions": TEST_ACTIONS,
                        },
                    }
                )
                return
            if path == TEST_SDK_PATH:
                self._send(
                    (
                        REPO_ROOT / "astrbot" / "dashboard" / "plugin_page_sdk.js"
                    ).read_bytes(),
                    content_type="application/javascript",
                    headers={
                        "Cache-Control": "public, max-age=31536000, immutable",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return
            if path == TEST_SESSION_PREFIX:
                if "astrbot_plugin_page=e2e-session-secret" not in self.headers.get(
                    "Cookie", ""
                ):
                    self._send(
                        b"Unauthorized",
                        content_type="text/plain",
                        status=HTTPStatus.UNAUTHORIZED,
                        headers={"Cache-Control": "no-store"},
                    )
                    return
                body, csp = _test_shell()
                self._send(
                    body,
                    content_type="text/html; charset=utf-8",
                    headers={
                        "Content-Security-Policy": csp,
                        "X-Content-Type-Options": "nosniff",
                        "Referrer-Policy": "no-referrer",
                        "Permissions-Policy": (
                            "camera=(), microphone=(), geolocation=(), payment=(), "
                            "usb=(), serial=(), bluetooth=()"
                        ),
                        "Cache-Control": "private, no-store",
                    },
                )
                return
            if path.startswith(TEST_BUNDLE_PREFIX):
                if any(
                    (
                        self.headers.get("Cookie"),
                        self.headers.get("Authorization"),
                        self.headers.get("X-API-Key"),
                        urlsplit(self.path).query,
                    )
                ):
                    self._send(
                        b"Forbidden",
                        content_type="text/plain",
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                origin = self.headers.get("Origin")
                if origin not in {None, "null", f"http://{HOST}:{DASHBOARD_PORT}"}:
                    self._send(
                        b"Forbidden",
                        content_type="text/plain",
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                asset = path.removeprefix(TEST_BUNDLE_PREFIX)
                if asset != "app.js":
                    self._send(
                        b"Not found",
                        content_type="text/plain",
                        status=HTTPStatus.NOT_FOUND,
                    )
                    return
                self._send(
                    TEST_PAGE_APP_JS,
                    content_type="application/javascript",
                    headers={
                        "Access-Control-Allow-Origin": origin or "null",
                        "Vary": "Origin",
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
                return
            if path in {TEST_INLINE_FILE_PATH, TEST_DOWNLOAD_FILE_PATH}:
                expected_secret = (
                    "inline-secret"
                    if path == TEST_INLINE_FILE_PATH
                    else "download-secret"
                )
                if (
                    f"astrbot_plugin_file={expected_secret}"
                    not in self.headers.get("Cookie", "")
                    or self.headers.get("Authorization")
                    or self.headers.get("X-API-Key")
                ):
                    self._send(
                        b"Unauthorized",
                        content_type="text/plain",
                        status=HTTPStatus.UNAUTHORIZED,
                        headers={"Cache-Control": "no-store"},
                    )
                    return
                attachment = path == TEST_DOWNLOAD_FILE_PATH
                self._send(
                    PIXEL_PNG,
                    content_type="image/png",
                    headers={
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                        "Content-Disposition": (
                            'attachment; filename="palette.png"'
                            if attachment
                            else 'inline; filename="palette.png"'
                        ),
                    },
                )
                return
            self._send_json(
                {"status": "ok", "message": None, "data": {}},
            )
            return
        if path == "/spike":
            with REQUESTS_LOCK:
                REQUESTS.clear()
            self._send(
                HOST_HTML,
                content_type="text/html; charset=utf-8",
                headers={
                    "Set-Cookie": (
                        f"{SESSION_COOKIE}; Path={SESSION_PREFIX}; HttpOnly; "
                        "SameSite=Strict; Max-Age=600"
                    ),
                    "Cache-Control": "no-store",
                },
            )
            return
        if path == "/spike/results":
            with REQUESTS_LOCK:
                body = json.dumps({"requests": REQUESTS}).encode()
            self._send(body, content_type="application/json")
            return
        if path == SDK_PATH:
            self._send(
                SDK_JS,
                content_type="application/javascript",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-Type-Options": "nosniff",
                },
            )
            return
        if path == SESSION_PREFIX:
            if SESSION_COOKIE not in self.headers.get("Cookie", ""):
                self._send(
                    b"Unauthorized",
                    content_type="text/plain",
                    status=HTTPStatus.UNAUTHORIZED,
                    headers={"Cache-Control": "no-store"},
                )
                return
            body, csp = _shell(self.server.server_port)
            self._send(
                body,
                content_type="text/html; charset=utf-8",
                headers={
                    "Content-Security-Policy": csp.decode(),
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "Permissions-Policy": (
                        "camera=(), microphone=(), geolocation=(), payment=(), "
                        "usb=(), serial=(), bluetooth=()"
                    ),
                    "Cache-Control": "private, no-store",
                },
            )
            return
        if path.startswith(BUNDLE_PREFIX):
            origin = self.headers.get("Origin")
            dashboard_origin = f"https://{HOST}:{self.server.server_port}"
            has_cookie = bool(self.headers.get("Cookie"))
            with REQUESTS_LOCK:
                REQUESTS.append(
                    {
                        "path": path,
                        "origin": origin,
                        "hasSessionCookie": has_cookie,
                    }
                )
            if origin not in {None, "null", dashboard_origin}:
                self._send(
                    b"Forbidden",
                    content_type="text/plain",
                    status=HTTPStatus.FORBIDDEN,
                    headers={"Cache-Control": "no-store"},
                )
                return
            name = path.removeprefix(BUNDLE_PREFIX)
            assets = {
                "app.js": (APP_JS, "application/javascript"),
                "static.js": (STATIC_JS, "application/javascript"),
                "dynamic.js": (DYNAMIC_JS, "application/javascript"),
                "style.css": (STYLE_CSS, "text/css"),
                "pixel.png": (PIXEL_PNG, "image/png"),
                "font.woff2": (FONT_PATH.read_bytes(), "font/woff2"),
            }
            asset = assets.get(name)
            if asset is None:
                self._send(
                    b"Not found",
                    content_type="text/plain",
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self._send(
                asset[0],
                content_type=asset[1],
                headers={
                    "Access-Control-Allow-Origin": origin or "null",
                    "Vary": "Origin",
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
            return
        self._send(
            b"Not found",
            content_type="text/plain",
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if self.server.server_port != BACKEND_PORT:
            self._send(
                b"Not found",
                content_type="text/plain",
                status=HTTPStatus.NOT_FOUND,
            )
            return
        if not self._require_authorized():
            return
        if path == (
            f"/api/v1/plugins/{TEST_EXTENSION_ID}/dashboard/pages/"
            f"{TEST_PAGE_ID}/session"
        ):
            payload = self._read_json()
            if payload.get("expected_generation") != TEST_GENERATION:
                self._send_json(
                    {"status": "error", "message": "Conflict", "data": None},
                    status=HTTPStatus.CONFLICT,
                )
                return
            self._send_json(
                {
                    "status": "ok",
                    "message": None,
                    "data": {
                        "protocol_version": 1,
                        "instance_id": TEST_INSTANCE_ID,
                        "plugin_generation": TEST_GENERATION,
                        "iframe_url": TEST_SESSION_PREFIX,
                        "handshake_nonce": TEST_NONCE,
                        "expires_at": "2099-07-17T12:00:00Z",
                    },
                },
                headers={
                    "Cache-Control": "no-store",
                    "Set-Cookie": (
                        "astrbot_plugin_page=e2e-session-secret; "
                        f"Path={TEST_SESSION_PREFIX}; HttpOnly; SameSite=Strict"
                    ),
                },
            )
            return
        action_prefix = f"/api/v1/plugins/{TEST_EXTENSION_ID}/dashboard/actions/"
        if path.startswith(action_prefix):
            action_id = path.removeprefix(action_prefix)
            if action_id == "config.fail":
                self._send_json(
                    {
                        "status": "error",
                        "message": "Fixture failure",
                        "data": None,
                    },
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                )
                return
            self._send_json(
                {
                    "status": "ok",
                    "message": None,
                    "data": {"enabled": True, "source": "e2e"},
                }
            )
            return
        upload_prefix = f"/api/v1/plugins/{TEST_EXTENSION_ID}/dashboard/uploads/"
        if path.startswith(upload_prefix):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length:
                self.rfile.read(length)
            self._send_json(
                {
                    "status": "ok",
                    "message": None,
                    "data": {"uploaded": True},
                }
            )
            return
        file_prefix = f"/api/v1/plugins/{TEST_EXTENSION_ID}/dashboard/files/"
        if path.startswith(file_prefix):
            payload = self._read_json()
            disposition = payload.get("expected_disposition")
            attachment = disposition == "attachment"
            ticket_path = (
                TEST_DOWNLOAD_FILE_PATH if attachment else TEST_INLINE_FILE_PATH
            )
            cookie_secret = "download-secret" if attachment else "inline-secret"
            self._send_json(
                {
                    "status": "ok",
                    "message": None,
                    "data": {
                        "ticket_url": ticket_path,
                        "filename": "palette.png",
                        "content_type": "image/png",
                        "size": len(PIXEL_PNG),
                        "disposition": disposition,
                        "expires_at": "2099-07-17T12:00:00Z",
                    },
                },
                headers={
                    "Cache-Control": "no-store",
                    "Set-Cookie": (
                        f"astrbot_plugin_file={cookie_secret}; Path={ticket_path}; "
                        "HttpOnly; SameSite=Strict"
                    ),
                },
            )
            return
        self._send_json(
            {"status": "error", "message": "Not found", "data": None},
            status=HTTPStatus.NOT_FOUND,
        )


def _create_tls_context(directory: Path) -> ssl.SSLContext:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "AstrBot plugin UI spike")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(HOST)), x509.DNSName("localhost")]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "certificate.pem"
    key_path = directory / "key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_path, key_path)
    return context


def main() -> None:
    global BACKEND_PORT, SPIKE_PORT, DASHBOARD_PORT

    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-port", type=int, default=BACKEND_PORT)
    parser.add_argument("--spike-port", type=int, default=SPIKE_PORT)
    parser.add_argument("--dashboard-port", type=int, default=DASHBOARD_PORT)
    args = parser.parse_args()
    BACKEND_PORT = args.backend_port
    SPIKE_PORT = args.spike_port
    DASHBOARD_PORT = args.dashboard_port
    with tempfile.TemporaryDirectory() as temp_directory:
        os.environ["ASTRBOT_ROOT"] = temp_directory
        os.environ["ASTRBOT_TEST_DASHBOARD_USERNAME"] = TEST_DASHBOARD_USER
        os.environ["ASTRBOT_TEST_DASHBOARD_TOKEN"] = TEST_DASHBOARD_TOKEN

        backend_server = ThreadingHTTPServer((HOST, args.backend_port), SpikeHandler)
        backend_thread = threading.Thread(
            target=backend_server.serve_forever,
            name="plugin-ui-e2e-backend",
            daemon=True,
        )
        backend_thread.start()

        server = ThreadingHTTPServer((HOST, args.spike_port), SpikeHandler)
        context = _create_tls_context(Path(temp_directory))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        try:
            server.serve_forever()
        finally:
            backend_server.shutdown()
            backend_server.server_close()
            backend_thread.join(timeout=5)


if __name__ == "__main__":
    main()
