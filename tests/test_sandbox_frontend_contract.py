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

    assert (
        "consoleHistory.value = [...consoleHistory.value]" in content
        or "await nextTick()" in content
    )


def test_sandbox_management_page_release_is_not_limited_to_dashboard_controller():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "item.controller_session_id === 'dashboard'" not in content
    assert "case 'release':" in content
    assert "return status !== 'stopping' && !!item.controller_session_id" in content


def test_sandbox_management_page_refreshes_list_after_immediate_create_success():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "const placeholder = { ...created, status: 'creating' as const }" in content
    assert "upsertSandboxRecord(placeholder)" in content
    assert (
        "const index = sandboxes.value.findIndex((item) => item.sandbox_id === record.sandbox_id)"
        in content
    )
    assert "next[index] = record" in content
    assert "sandboxes.value = next" in content


def test_sandbox_management_page_keeps_create_button_available_while_other_sandboxes_are_creating():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert 'prepend-icon="mdi-plus" @click="createDialog = true"' in content
    assert 'prepend-icon="mdi-plus" :disabled="creatingRequestPending"' not in content
    assert ':disabled="createFlowActive"' not in content
    assert ':disabled="!hasProviderOptions || creatingRequestPending"' in content


def test_sandbox_management_page_tracks_multiple_pending_creates_instead_of_single_id():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "pendingCreateSandboxes" in content
    assert "pendingCreateSandboxId" not in content


def test_sandbox_management_page_loads_provider_options_from_api():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "const providerOptions = [" not in content
    assert "axios.get('/api/sandbox/providers'" in content
    assert "providerOptions.value = providers.map(" in content


def test_sandbox_management_page_does_not_show_legacy_provider_hint():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "tm('create.providerHint')" not in content


def test_sandbox_management_page_does_not_allow_configure_while_creating():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "case 'configure':" in content
    assert "return status !== 'creating' && status !== 'stopping'" in content


def test_sandbox_management_page_does_not_toast_running_after_create():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "toast(tm('messages.createReady'))" not in content


def test_sandbox_management_page_splits_running_into_busy_and_available_labels():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "return hasController(item) ? 'busy' : 'available'" in content


def test_sandbox_i18n_uses_status_and_idle_labels():
    zh = (ROOT / "dashboard/src/i18n/locales/zh-CN/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    en = (ROOT / "dashboard/src/i18n/locales/en-US/features/sandbox.json").read_text(
        encoding="utf-8"
    )

    assert '"status": "状态"' in zh
    assert '"available": "空闲"' in zh
    assert '"status": "Status"' in en
    assert '"available": "Idle"' in en
