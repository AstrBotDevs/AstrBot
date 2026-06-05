from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_DEFAULT_IP_SERVICES = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)


def _read_url(url: str, timeout: int = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace").strip()


def _resolve_public_ip(auto_acme_config: dict[str, Any]) -> str:
    configured_ip = str(
        os.environ.get("ASTRBOT_DASHBOARD_ACME_IP")
        or auto_acme_config.get("ip")
        or ""
    ).strip()
    if configured_ip:
        return configured_ip

    services = auto_acme_config.get("ip_services") or _DEFAULT_IP_SERVICES
    if not isinstance(services, list):
        services = list(_DEFAULT_IP_SERVICES)

    last_error: Exception | None = None
    for service in services:
        try:
            ip = _read_url(str(service)).strip()
            if ip:
                return ip
        except Exception as e:  # pragma: no cover - network dependent
            last_error = e
            logger.debug(f"Failed to get public IP from {service}: {e}")

    raise RuntimeError(f"Unable to resolve public IP for ACME certificate: {last_error}")


def _find_acme_sh() -> str | None:
    candidates = [
        os.environ.get("ACME_SH"),
        os.path.expanduser("~/.acme.sh/acme.sh"),
        shutil.which("acme.sh"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).expanduser())
    return None


def _install_acme_sh(email: str) -> str:
    logger.info("acme.sh not found. Installing acme.sh for dashboard HTTPS ACME.")
    installer = _read_url("https://get.acme.sh", timeout=30)
    cmd = ["sh", "-s"]
    if email:
        cmd.append(f"email={email}")
    subprocess.run(
        cmd,
        input=installer,
        text=True,
        check=True,
        timeout=180,
    )
    acme_sh = _find_acme_sh()
    if not acme_sh:
        raise RuntimeError("acme.sh installation finished but acme.sh was not found")
    return acme_sh


def _run_acme(args: list[str], timeout: int) -> None:
    logger.debug("Running ACME command: %s", " ".join(args))
    subprocess.run(args, check=True, timeout=timeout)


def ensure_dashboard_ip_certificate(
    ssl_config: dict[str, Any],
) -> tuple[bool, dict[str, str]]:
    """Ensure a Let's Encrypt certificate for the dashboard public IP.

    This uses acme.sh standalone HTTP-01 mode, similar to 3x-ui's shell helper.
    Port 80 must be reachable from the public Internet and not occupied.
    Returns (changed, paths). ``changed`` means ssl_config was updated.
    """
    auto_acme_config = ssl_config.get("auto_acme", {})
    if not isinstance(auto_acme_config, dict):
        auto_acme_config = {}

    enabled = bool(
        os.environ.get("ASTRBOT_DASHBOARD_ACME_ENABLE", "").lower()
        in ("1", "true", "yes", "on")
        or auto_acme_config.get("enable", False)
    )
    if not enabled:
        return False, {}

    cert_file = str(ssl_config.get("cert_file") or "").strip()
    key_file = str(ssl_config.get("key_file") or "").strip()
    force_issue = bool(auto_acme_config.get("force_issue", False))
    if (
        cert_file
        and key_file
        and Path(cert_file).expanduser().is_file()
        and Path(key_file).expanduser().is_file()
        and not force_issue
    ):
        return False, {"cert_file": cert_file, "key_file": key_file}

    public_ip = _resolve_public_ip(auto_acme_config)
    email = str(
        os.environ.get("LE_EMAIL")
        or os.environ.get("ASTRBOT_DASHBOARD_ACME_EMAIL")
        or auto_acme_config.get("email")
        or ""
    ).strip()
    server = str(auto_acme_config.get("server") or "letsencrypt").strip()
    keylength = str(auto_acme_config.get("keylength") or "2048").strip()
    certificate_profile = str(
        auto_acme_config.get("certificate_profile") or "shortlived"
    ).strip()
    days = str(auto_acme_config.get("days") or "6").strip()
    httpport = str(auto_acme_config.get("httpport") or "80").strip()
    timeout = int(auto_acme_config.get("timeout", 600))

    cert_dir = Path(
        auto_acme_config.get("cert_dir")
        or Path(get_astrbot_data_path()) / "certs" / "dashboard-acme" / public_ip
    ).expanduser()
    cert_dir.mkdir(parents=True, exist_ok=True)
    fullchain_path = cert_dir / "fullchain.pem"
    key_path = cert_dir / "privkey.pem"

    acme_sh = _find_acme_sh() or _install_acme_sh(email)

    _run_acme([acme_sh, "--set-default-ca", "--server", server], timeout=120)

    issue_cmd = [
        acme_sh,
        "--issue",
        "--server",
        server,
        "-d",
        public_ip,
        "--standalone",
        "--keylength",
        keylength,
        "--certificate-profile",
        certificate_profile,
        "--days",
        days,
        "--httpport",
        httpport,
    ]
    if force_issue:
        issue_cmd.append("--force")
    _run_acme(issue_cmd, timeout=timeout)

    install_cmd = [
        acme_sh,
        "--install-cert",
        "-d",
        public_ip,
        "--fullchain-file",
        str(fullchain_path),
        "--key-file",
        str(key_path),
    ]
    _run_acme(install_cmd, timeout=timeout)

    if not fullchain_path.is_file() or not key_path.is_file():
        raise RuntimeError("ACME certificate files were not created")

    ssl_config["cert_file"] = str(fullchain_path)
    ssl_config["key_file"] = str(key_path)
    logger.info("Dashboard HTTPS IP certificate is ready for %s.", public_ip)
    return True, {"cert_file": str(fullchain_path), "key_file": str(key_path)}
