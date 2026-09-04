"""Regression checks for secure, functional container deployment defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relative_path",
    [
        "k8s/astrbot/02-deployment.yaml",
        "k8s/astrbot_with_napcat/02-deployment.yaml",
    ],
)
def test_kubernetes_dashboard_is_reachable_only_via_container_mode(
    relative_path: str,
) -> None:
    deployment = yaml.safe_load(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )
    containers = deployment["spec"]["template"]["spec"]["containers"]
    astrbot = next(container for container in containers if container["name"] == "astrbot")
    environment = {item["name"]: item["value"] for item in astrbot.get("env", [])}

    assert environment["ASTRBOT_DASHBOARD_HOST"] == "0.0.0.0"
    assert environment["ASTRBOT_DASHBOARD_ACCESS_MODE"] == "container_loopback"


@pytest.mark.parametrize(
    "relative_path",
    [
        "k8s/astrbot/03-service-nodeport.yaml",
        "k8s/astrbot_with_napcat/03-service-nodeport.yaml",
    ],
)
def test_default_kubernetes_services_are_cluster_internal(relative_path: str) -> None:
    service = yaml.safe_load(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )
    assert service["spec"]["type"] == "ClusterIP"


@pytest.mark.parametrize("relative_path", ["compose.yml", "compose-with-shipyard.yml"])
def test_compose_dashboard_is_published_on_host_loopback(relative_path: str) -> None:
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )
    ports = [str(port) for port in compose["services"]["astrbot"]["ports"]]
    assert "127.0.0.1:6185:6185" in ports
    assert all(":6199" not in port for port in ports)
