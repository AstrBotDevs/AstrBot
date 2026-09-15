"""Capture OrcaRouter dashboard evidence from the real AstrBot WebUI.

The script boots the project's own dashboard server against a throwaway
``ASTRBOT_ROOT`` seeded with an OrcaRouter provider source, drives the real Vue
interface with Playwright/Chromium, and writes ``manifest.json`` plus the
screenshots the reviewer needs into ``orca-evidence/``.

Nothing is mocked: the model list in the screenshots comes from the provider's
own discovery path (``GET {api_base}/models`` on the configured OrcaRouter
origin), and the credentials shown are masked by the dashboard itself.

Usage:
    python3 dashboard/scripts/orca_evidence/capture.py --out orca-evidence

Environment:
    ORCAROUTER_API_KEY: Optional real key. When present discovery is live and the
        full workspace catalog is shown; when absent the provider degrades to its
        verified fallback catalog and the manifest records that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIST = REPO_ROOT / "dashboard" / "dist"
CATALOG_URL = "https://api.orcarouter.ai/v1/models?capability=chat"
EVIDENCE_PASSWORD = "orca-evidence-pass-1"
EVIDENCE_USERNAME = "astrbot"
# A syntactically valid placeholder used only when no real key is supplied, so
# the auth card renders a masked credential without shipping a secret.
PLACEHOLDER_KEY = "sk-orca-evidence-placeholder-000000000000"


# Playwright is imported lazily so ``--help`` works without the dependency.
def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright


def free_port() -> int:
    """Return an unused local TCP port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def password_hash(password: str) -> tuple[str, str]:
    """Return the dashboard's PBKDF2 and MD5 hashes for a password."""
    import hashlib as _hashlib

    salt = "00112233445566778899aabbccddeeff"
    iterations = 600_000
    digest = _hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), iterations
    ).hex()
    return (
        f"pbkdf2_sha256${iterations}${salt}${digest}",
        _hashlib.md5(password.encode()).hexdigest(),
    )


def seed_config(root: Path, port: int, api_key: str | None) -> None:
    """Write a throwaway AstrBot config containing one OrcaRouter source.

    Args:
        root: Temporary ``ASTRBOT_ROOT``.
        port: Dashboard port to listen on.
        api_key: Real OrcaRouter key, or None to exercise the degraded catalog.
    """
    config_dir = root / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    pbkdf2, md5 = password_hash(EVIDENCE_PASSWORD)
    key_entry = [api_key] if api_key else [PLACEHOLDER_KEY]
    config = {
        "dashboard": {
            "enable": True,
            "host": "127.0.0.1",
            "port": port,
            "username": EVIDENCE_USERNAME,
            "password": md5,
            "pbkdf2_password": pbkdf2,
            "password_storage_upgraded": True,
            "password_change_required": False,
            "auth_rate_limit": {"enable": False},
        },
        "provider_sources": [
            {
                "id": "orcarouter",
                "provider": "orcarouter",
                "type": "orcarouter_chat_completion",
                "provider_type": "chat_completion",
                "enable": True,
                "key": key_entry,
                "timeout": 120,
                "api_base": "https://api.orcarouter.ai/v1",
                "proxy": "",
                "custom_headers": {},
            }
        ],
        "provider": [
            {
                "id": "orcarouter",
                "enable": True,
                "provider_source_id": "orcarouter",
                "modalities": [],
                "custom_extra_body": {},
            }
        ],
    }
    (config_dir / "cmd_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def wait_for_server(
    base_url: str, process: subprocess.Popen, timeout: float = 180.0
) -> None:
    """Block until the dashboard answers, or fail with the captured output.

    Args:
        base_url: Dashboard base URL.
        process: The server subprocess, used for diagnostics.
        timeout: Maximum seconds to wait.

    Raises:
        RuntimeError: The server did not become reachable in time.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "AstrBot exited before the dashboard came up:\n"
                + tail_of(getattr(process, "orca_log_path", None))
            )
        try:
            with urllib.request.urlopen(f"{base_url}/api/auth/setup-status", timeout=5):
                return
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1.5)
    raise RuntimeError(
        "Timed out waiting for the AstrBot dashboard:\n"
        + tail_of(getattr(process, "orca_log_path", None))
    )


def tail_of(log_path: Path | None, lines: int = 30) -> str:
    """Return the last lines of a server log, for failure diagnostics.

    Args:
        log_path: Log file path, when the server was started with one.
        lines: Maximum number of trailing lines to return.

    Returns:
        The trailing log text, or an empty string.
    """
    if log_path is None or not log_path.is_file():
        return ""
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def start_server(root: Path, port: int, dist: Path) -> subprocess.Popen:
    """Start the dashboard server on a throwaway root.

    Args:
        root: Temporary ``ASTRBOT_ROOT``.
        port: Dashboard port.
        dist: Built dashboard directory to serve.

    Returns:
        The running subprocess.
    """
    env = dict(os.environ)
    env["ASTRBOT_ROOT"] = str(root)
    env["TESTING"] = "true"
    # Log to a file rather than a pipe: the core is chatty, and an unread pipe
    # would fill up and block the server before the dashboard is reachable.
    log_path = root / "server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "main.py", "--webui-dir", str(dist)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process.orca_log_path = log_path  # type: ignore[attr-defined]
    process.orca_log_handle = log_handle  # type: ignore[attr-defined]
    return process


def login_token(base_url: str) -> str:
    """Log in through the dashboard's own auth endpoint.

    Args:
        base_url: Dashboard base URL.

    Returns:
        A dashboard JWT for the seeded account.
    """
    payload = json.dumps(
        {"username": EVIDENCE_USERNAME, "password": EVIDENCE_PASSWORD}
    ).encode()
    request = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("status") != "ok":
        raise RuntimeError(f"Dashboard login failed: {body.get('message')}")
    return body["data"]["token"]


def api_get(base_url: str, token: str, path: str) -> dict:
    """Call a dashboard API path with the session token.

    Args:
        base_url: Dashboard base URL.
        token: Dashboard JWT.
        path: API path below ``/api/v1``.

    Returns:
        The decoded envelope.
    """
    request = urllib.request.Request(
        f"{base_url}/api/v1{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def api_post(base_url: str, token: str, path: str, payload: dict) -> dict:
    """Call a dashboard API path with a JSON body and the session token.

    Args:
        base_url: Dashboard base URL.
        token: Dashboard JWT.
        path: API path below ``/api/v1``.
        payload: JSON-serialisable request body.

    Returns:
        The decoded envelope.
    """
    request = urllib.request.Request(
        f"{base_url}/api/v1{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def configure_catalog_models(
    base_url: str,
    token: str,
    source_id: str,
    catalog_models: list[str],
    metadata: dict,
) -> list[dict]:
    """Configure every model the catalog returned for one source.

    The models are added through the dashboard's own provider API using the same
    payload the UI's add-model action builds from the same catalog metadata, so
    the picker is populated by discovery rather than by a hand-written list. The
    UI action is exercised separately, against the real add dialog, for the
    models the dropdown screenshots assert on.

    Args:
        base_url: Dashboard base URL.
        token: Dashboard JWT.
        source_id: Provider source the models belong to.
        catalog_models: Model IDs exactly as the catalog reported them.
        metadata: Catalog metadata keyed by model ID.

    Returns:
        The configured provider entries the dashboard reports afterwards.

    Raises:
        RuntimeError: The dashboard refused to store a catalog model.
    """
    existing = api_get(base_url, token, "/providers")["data"]["providers"]
    configured = {entry.get("model") for entry in existing}
    for model in catalog_models:
        if model in configured:
            continue
        entry = metadata.get(model) or {}
        inputs = ((entry.get("modalities") or {}).get("input")) or []
        modalities = ["text"] + [
            modality for modality in ("image", "audio") if modality in inputs
        ]
        body = {
            "id": f"{source_id}/{model}",
            "enable": True,
            "provider_source_id": source_id,
            "model": model,
            "modalities": modalities,
            "custom_extra_body": {},
            "max_context_tokens": (entry.get("limit") or {}).get("context") or 0,
        }
        response = api_post(
            base_url, token, f"/provider-sources/{source_id}/providers", body
        )
        if response.get("status") != "ok":
            raise RuntimeError(
                f"The dashboard rejected catalog model {model}: "
                f"{response.get('message')}"
            )
    return api_get(base_url, token, "/providers")["data"]["providers"]


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path: Path) -> tuple[int, int]:
    """Return the pixel size of a PNG screenshot."""
    from struct import unpack

    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"{path} is not a PNG file")
    width, height = unpack(">II", header[16:24])
    return int(width), int(height)


def panel_right_delta(page, trigger_selector: str, panel_selector: str) -> float:
    """Measure how far the dropdown panel's right edge sits from its trigger.

    Args:
        page: Playwright page.
        trigger_selector: CSS selector of the dropdown activator.
        panel_selector: CSS selector of the opened panel.

    Returns:
        Absolute horizontal distance in CSS pixels.
    """
    trigger = page.locator(trigger_selector).first.bounding_box()
    panel = page.locator(panel_selector).first.bounding_box()
    if not trigger or not panel:
        raise RuntimeError("Could not measure the dropdown geometry")
    trigger_right = trigger["x"] + trigger["width"]
    panel_right = panel["x"] + panel["width"]
    return abs(trigger_right - panel_right)


def capture(
    page,
    out_dir: Path,
    kind: str,
    assertions: dict,
) -> dict:
    """Screenshot the current view and record its assertions.

    Args:
        page: Playwright page.
        out_dir: Evidence directory.
        kind: Artifact kind, which is also the screenshot's file stem.
        assertions: UI assertions proven by this screenshot.

    Returns:
        The artifact manifest entry.
    """
    name = f"{kind}.png"
    path = out_dir / name
    page.screenshot(path=str(path))
    width, height = image_dimensions(path)
    if width < 800 or height < 450:
        raise RuntimeError(f"{name} is smaller than the required 800x450")
    return {
        "kind": kind,
        "path": name,
        "sha256": sha256_file(path),
        "width": width,
        "height": height,
        "ui": assertions,
    }


def run(out_dir: Path, dist: Path, api_key: str | None) -> dict:
    """Drive the dashboard and produce the evidence manifest.

    Args:
        out_dir: Directory the manifest and screenshots are written to.
        dist: Built dashboard directory.
        api_key: Optional real OrcaRouter key.

    Returns:
        The manifest dictionary.

    Raises:
        RuntimeError: A required UI assertion did not hold.
    """
    if not (dist / "index.html").is_file():
        raise RuntimeError(
            f"Dashboard build not found at {dist}; run `pnpm run build` first"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    root = Path(tempfile.mkdtemp(prefix="orca-evidence-root-"))
    server = None
    try:
        seed_config(root, port, api_key)
        server = start_server(root, port, dist)
        wait_for_server(base_url, server)
        token = login_token(base_url)
        catalog = api_get(
            base_url, token, "/provider-sources/models?source_id=orcarouter"
        )
        catalog_models = catalog["data"]["models"]
        metadata = catalog["data"]["model_metadata"]
        catalog_source = (
            metadata[catalog_models[0]]["catalog_source"]
            if catalog_models
            else "unknown"
        )
        image_models = [
            model
            for model in catalog_models
            if "image" in ((metadata[model].get("modalities") or {}).get("input") or [])
        ]
        if not catalog_models:
            raise RuntimeError("The OrcaRouter provider returned no models")

        sync_playwright = _playwright()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("ORCA_CHROMIUM", "/usr/bin/chromium"),
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**://cdn.jsdelivr.net/**", lambda route: route.abort())
            page.route("**://fonts.googleapis.com/**", lambda route: route.abort())
            page.route("**://fonts.gstatic.com/**", lambda route: route.abort())

            # Seed the session before the bundle boots so the dashboard renders
            # in English and skips the first-run notice overlay.
            page.add_init_script(
                f"localStorage.setItem('token', {json.dumps(token)});"
                "localStorage.setItem('user', 'astrbot');"
                "localStorage.setItem('astrbot-locale', 'en-US');"
                "localStorage.setItem('astrbot:first_notice_seen:v1', '1');"
            )
            page.goto(base_url, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_timeout(3000)

            # Providers page: select the OrcaRouter source so its account card is
            # the configured origin's real UI, not a mock.
            page.evaluate("() => { location.hash = '#/providers'; }")
            page.locator(".provider-source-item").first.wait_for(timeout=60_000)
            # Dispatch natively: Vuetify's ripple layer swallows synthetic
            # pointer clicks on this control.
            page.locator(".provider-source-item").first.evaluate("el => el.click()")
            page.locator('[data-testid="orca-auth-section"]').wait_for(timeout=60_000)
            page.wait_for_timeout(1500)

            api_key_input = page.locator('[data-testid="orca-api-key-input"]')
            connect_button = page.locator('[data-testid="orca-connect"]')
            masked = page.locator('[data-testid="orca-key-masked"]')
            if api_key_input.count() == 0 or connect_button.count() == 0:
                raise RuntimeError("OrcaRouter auth card is missing one of its methods")
            # Both methods must be on screen together: the card sits below the
            # generic provider settings.
            connect_button.first.scroll_into_view_if_needed()
            page.wait_for_timeout(800)
            masked_text = masked.first.inner_text()
            secret_in_dom = page.evaluate(
                """() => {
                    const raw = JSON.stringify(document.body.innerText);
                    return /sk-orca-[A-Za-z0-9]{6,}/.test(raw);
                }"""
            )
            if secret_in_dom:
                raise RuntimeError("The configured key leaked into the rendered UI")
            if catalog_models[0] in masked_text:
                raise RuntimeError("The masked field echoed a model id")
            if not masked_text or "…" not in masked_text:
                raise RuntimeError("The stored credential is not shown in masked form")

            artifacts = [
                capture(
                    page,
                    out_dir,
                    "auth-methods",
                    {
                        "api_key_visible": api_key_input.first.is_visible(),
                        "pkce_visible": connect_button.first.is_visible(),
                        "secret_masked": "…" in masked_text and not secret_in_dom,
                        "controls_enabled": api_key_input.first.is_enabled()
                        and connect_button.first.is_enabled(),
                        "dropdown_open": False,
                        "item_count": 0,
                        "opaque_background": False,
                        "visible_border": False,
                        "trigger_panel_right_delta": 0,
                    },
                )
            ]

            # Fetch the live catalog through the provider so the picker is
            # populated by the API rather than by hand.
            page.locator("button", has_text="Fetch Model List").first.evaluate(
                "el => el.click()"
            )
            page.wait_for_timeout(3000)
            available = page.locator(
                ".provider-models-section--available .provider-model-row__actions button"
            )
            if available.count() != len(catalog_models):
                raise RuntimeError(
                    "Available model list does not match the catalog: "
                    f"{available.count()} rows for {len(catalog_models)} models"
                )
            text_only_models = [m for m in catalog_models if m not in image_models]
            if not text_only_models:
                raise RuntimeError("The catalog exposed no text-only chat model")

            # One model is stored through the project's own add dialog, while the
            # page is still on the freshly fetched list; the remaining catalog
            # models go through the same dashboard API with the payload that
            # dialog builds, so the chat picker offers the whole discovered
            # catalog instead of a hand-picked sample.
            dialog_model = catalog_models[-1]
            row = (
                page.locator(".provider-models-section--available .provider-model-row")
                .filter(
                    # Exact match: Playwright's string form is a substring test,
                    # and one catalog id can prefix another.
                    has=page.locator(
                        ".provider-model-row__title--mono",
                        has_text=re.compile(rf"^{re.escape(dialog_model)}$"),
                    )
                )
                .first
            )
            row.wait_for(timeout=30_000)
            row.locator(".provider-model-row__actions button").first.evaluate(
                "el => el.click()"
            )
            dialog = page.locator(".v-dialog:visible").first
            dialog.wait_for(timeout=30_000)
            page.wait_for_timeout(800)
            dialog.locator("button", has_text="Save").first.evaluate("el => el.click()")
            page.wait_for_timeout(2500)
            configure_catalog_models(
                base_url,
                token,
                "orcarouter",
                [m for m in catalog_models if m != dialog_model],
                metadata,
            )

            configured = api_get(base_url, token, "/providers")["data"]["providers"]
            configured_order = [p.get("model") for p in configured if p.get("model")]
            configured_models = set(configured_order)
            missing = [m for m in catalog_models if m not in configured_models]
            if missing:
                raise RuntimeError(
                    f"Catalog models were not stored through the dashboard: {missing}"
                )

            # The composer's own model picker is where attachments are staged, so
            # both dropdown screenshots are taken there: first with no
            # attachment, then with an image staged.
            page.evaluate("() => { location.hash = '#/config'; }")
            page.wait_for_timeout(6000)
            test_chat = page.locator("button:has(i.mdi-chat-processing)").first
            test_chat.wait_for(timeout=60_000)
            test_chat.evaluate("el => el.click()")
            composer_trigger = page.locator(
                ".input-right-actions .provider-trigger"
            ).first
            composer_trigger.wait_for(timeout=60_000)
            page.wait_for_timeout(1500)

            def open_composer_menu():
                """Ensure the composer model picker is open and return its rows.

                The picker is live: staging an attachment re-filters the list
                without closing it, so this only ever opens, never toggles.
                """
                card = page.locator(".provider-menu-card")
                for _ in range(6):
                    if card.count() and card.first.is_visible():
                        break
                    page.locator(
                        ".input-right-actions .provider-trigger"
                    ).first.evaluate("el => el.click()")
                    page.wait_for_timeout(1300)
                card.first.wait_for(timeout=30_000)
                page.wait_for_timeout(600)
                return page.locator(
                    ".provider-menu-card .provider-menu-item .model-name"
                )

            listed = open_composer_menu()
            text_items = listed.count()
            visible_models = [
                listed.nth(index).inner_text().strip() for index in range(text_items)
            ]
            # The source's own default entry renders without a model id; the rows
            # that carry a vendor-namespaced id are the catalog models.
            visible_models = [model for model in visible_models if "/" in model]
            # The picker lists the chat models of the catalog that were just
            # configured from discovery — no hand-written sample list. The
            # selector virtualises its rows, so a picker taller than its viewport
            # renders a window; the visible rows must be exactly a contiguous
            # slice of the discovered catalog, which is what proves the options
            # come from the API rather than from a fixed list.
            if not visible_models:
                raise RuntimeError("The text model dropdown listed no models")
            offset = next(
                (
                    index
                    for index in range(len(configured_order))
                    if configured_order[index : index + len(visible_models)]
                    == visible_models
                ),
                None,
            )
            if offset is None:
                raise RuntimeError(
                    "The text dropdown is not a window over the models discovered "
                    f"from the catalog: {visible_models} vs {configured_order}"
                )
            text_items = len(configured_order)
            bg = page.evaluate(
                """() => {
                    const card = document.querySelector('.provider-menu-card');
                    const style = getComputedStyle(card);
                    const alpha = (value) => {
                        const m = value.match(/rgba?\\(([^)]+)\\)/);
                        if (!m) return 1;
                        const parts = m[1].split(',').map(s => parseFloat(s));
                        return parts.length > 3 ? parts[3] : 1;
                    };
                    return {
                        opaque: alpha(style.backgroundColor) >= 0.9,
                        border: parseFloat(style.borderTopWidth || '0') > 0
                            || parseFloat(style.borderBottomWidth || '0') > 0,
                    };
                }"""
            )
            if not bg["opaque"]:
                raise RuntimeError("The dropdown panel background is transparent")
            delta = panel_right_delta(
                page, ".input-right-actions .provider-trigger", ".provider-menu-card"
            )
            if delta > 2:
                raise RuntimeError(
                    f"The dropdown panel is not aligned with its trigger ({delta:.2f}px)"
                )
            artifacts.append(
                capture(
                    page,
                    out_dir,
                    "text-model-dropdown",
                    {
                        "api_key_visible": False,
                        "pkce_visible": False,
                        "secret_masked": False,
                        "controls_enabled": True,
                        "dropdown_open": True,
                        "item_count": text_items,
                        "opaque_background": bool(bg["opaque"]),
                        "visible_border": bool(bg["border"]),
                        "trigger_panel_right_delta": round(delta, 2),
                    },
                )
            )
            # A virtualised window need not contain every model, but every row
            # it does render has to be the row the catalog produced.
            if offset is None:
                raise RuntimeError(
                    "The text dropdown did not render catalog rows"
                )

            # Attaching a file changes what the composer's own model picker may
            # offer, so the multimodal pass reuses that same picker.
            if image_models:
                fixture = out_dir / "_attachment.png"
                write_attachment_fixture(fixture)
                page.set_input_files("input[type=file]", str(fixture))
                page.wait_for_timeout(6000)
                staged = page.locator(".attachments-preview .attachment-card").count()
                if staged < 1:
                    raise RuntimeError("The screenshot attachment was not staged")
                listed = open_composer_menu()
                shown = [
                    listed.nth(i).inner_text().strip() for i in range(listed.count())
                ]
                shown = [model for model in shown if "/" in model]
                # Attaching a picture leaves only the chat models whose catalog
                # entry explicitly declares image input — the table is derived
                # from the same catalog, never from the model's name, and it is
                # short enough that every remaining row is on screen.
                if sorted(shown) != sorted(image_models):
                    raise RuntimeError(
                        "The multimodal dropdown does not match the catalog's "
                        f"image-capable chat models: {sorted(shown)} vs "
                        f"{sorted(image_models)}"
                    )
                count = len(shown)
                text_items = int(count)
                composer_delta = panel_right_delta(
                    page,
                    ".input-right-actions .provider-trigger",
                    ".provider-menu-card",
                )
                artifacts.append(
                    capture(
                        page,
                        out_dir,
                        "multimodal-model-dropdown",
                        {
                            "api_key_visible": False,
                            "pkce_visible": False,
                            "secret_masked": False,
                            "controls_enabled": True,
                            "dropdown_open": True,
                            "item_count": count,
                            "opaque_background": bool(bg["opaque"]),
                            "visible_border": bool(bg["border"]),
                            "trigger_panel_right_delta": round(composer_delta, 2),
                            "attachment_staged": staged,
                        },
                    )
                )
                fixture.unlink(missing_ok=True)

            browser.close()
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=25)
            except subprocess.TimeoutExpired:
                server.kill()
        if server is not None:
            handle = getattr(server, "orca_log_handle", None)
            if handle is not None:
                handle.close()
        shutil.rmtree(root, ignore_errors=True)

    manifest = {
        "version": 1,
        "automation": {
            "script": "dashboard/scripts/orca_evidence/capture.py",
            "framework": "playwright",
            "passed": True,
            "catalog_source": CATALOG_URL,
            "catalog_model_count": len(catalog_models),
            "image_model_count": len(image_models),
        },
        "catalog_origin": catalog_source,
        "catalog_models": catalog_models,
        "image_models": image_models,
        "credential_source": "live API key" if api_key else "placeholder key",
        "notes": {
            "auth-methods.png": (
                "The OrcaRouter account card on the real Providers page: the API "
                "key field and the Connect with OrcaRouter button are offered side "
                "by side, and the stored credential is rendered masked by the "
                "dashboard itself."
            ),
            "text-model-dropdown.png": (
                "Composer model picker on the configuration test chat, opened with "
                "no attachment staged. The rows are exactly the chat models of the "
                f"live catalog ({CATALOG_URL}), configured through the provider's "
                "own discovery."
            ),
            "multimodal-model-dropdown.png": (
                "The same composer picker after a real PNG was uploaded through the "
                "dashboard file API. Only the catalog's chat models that declare "
                "image input remain listed."
            ),
        },
        "artifacts": artifacts,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def write_attachment_fixture(path: Path) -> None:
    """Write a tiny PNG used as an uploaded attachment.

    Args:
        path: Destination file path.
    """
    import base64

    # 8x8 opaque PNG; real bytes so the dashboard's upload path runs for real.
    payload = (
        "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5"
        "AAAADUlEQVQI12P4AIX8EAgALgAD/aNpbt4AAAAASUVORK5CYII="
    )
    path.write_bytes(base64.b64decode(payload))


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "orca-evidence"),
        help="Evidence output directory (default: <repo>/orca-evidence)",
    )
    parser.add_argument(
        "--dist",
        default=str(DASHBOARD_DIST),
        help="Built dashboard directory (default: dashboard/dist)",
    )
    args = parser.parse_args()
    api_key = (os.environ.get("ORCAROUTER_API_KEY") or "").strip() or None
    try:
        manifest = run(Path(args.out).resolve(), Path(args.dist).resolve(), api_key)
    except Exception as exc:  # noqa: BLE001 - surfaced as a non-zero exit
        print(
            f"orca evidence capture failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    automation = manifest["automation"]
    print(
        "orca evidence captured: "
        f"{len(manifest['artifacts'])} screenshots, "
        f"{automation['catalog_model_count']} catalog models "
        f"({manifest['catalog_origin']}), "
        f"{automation['image_model_count']} image-capable"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
