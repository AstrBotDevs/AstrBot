from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sandbox_management_page_exists():
    assert (ROOT / "dashboard/src/views/SandboxManagementPage.vue").is_file()


def test_main_routes_include_sandboxes_page():
    content = (ROOT / "dashboard/src/router/MainRoutes.ts").read_text(encoding="utf-8")

    assert "name: 'Sandboxes'" in content
    assert "path: '/sandboxes'" in content
    assert "SandboxManagementPage.vue" in content


def test_sidebar_includes_sandboxes_navigation():
    content = (
        ROOT / "dashboard/src/layouts/full/vertical-sidebar/sidebarItem.ts"
    ).read_text(encoding="utf-8")

    assert "core.navigation.sandboxes" in content
    assert "to: '/sandboxes'" in content


def test_sandbox_management_page_uses_current_sandbox_api_prefix():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "/api/sandboxes" not in content
    assert "/api/sandbox" in content


def test_sandbox_management_page_does_not_gate_destroy_by_provider_capability():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "hasCapability(item, 'destroy')" not in content


def test_sandbox_management_page_replaces_console_history_after_command_updates():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "consoleHistory.value = [...consoleHistory.value]" in content or "await nextTick()" in content


def test_sandbox_management_page_release_is_not_limited_to_dashboard_controller():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "item.controller_session_id === 'dashboard'" not in content
    assert "return !!item.controller_session_id" in content


def test_sandbox_i18n_uses_status_and_idle_labels():
    zh = (ROOT / "dashboard/src/i18n/locales/zh-CN/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    en = (ROOT / "dashboard/src/i18n/locales/en-US/features/sandbox.json").read_text(
        encoding="utf-8"
    )

    assert '"lease": "状态"' in zh
    assert '"available": "空闲"' in zh
    assert '"lease": "Status"' in en
    assert '"available": "Idle"' in en
