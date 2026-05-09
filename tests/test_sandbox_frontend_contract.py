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
