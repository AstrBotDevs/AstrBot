from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def has_quote_style(content: str, snippet: str) -> bool:
    return snippet in content or snippet.replace("'", '"') in content


def test_sandbox_management_page_exists():
    assert (ROOT / "dashboard/src/views/SandboxManagementPage.vue").is_file()


def test_main_routes_include_sandboxes_page():
    content = (ROOT / "dashboard/src/router/MainRoutes.ts").read_text(encoding="utf-8")

    assert has_quote_style(content, "name: 'Sandboxes'")
    assert has_quote_style(content, "path: '/sandboxes'")
    assert "SandboxManagementPage.vue" in content


def test_sidebar_includes_sandboxes_navigation():
    content = (
        ROOT / "dashboard/src/layouts/full/vertical-sidebar/sidebarItem.ts"
    ).read_text(encoding="utf-8")

    assert "core.navigation.sandboxes" in content
    assert has_quote_style(content, "to: '/sandboxes'")


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


def test_sandbox_management_page_disables_destroy_for_occupied_sandboxes():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "case 'destroy':")
    assert has_quote_style(
        content, "return status !== 'stopping' && !item.controller_session_id"
    )


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

    assert not has_quote_style(content, "item.controller_session_id === 'dashboard'")
    assert has_quote_style(content, "case 'release':")
    assert has_quote_style(
        content, "return status !== 'stopping' && !!item.controller_session_id"
    )


def test_sandbox_management_page_uses_backend_create_record_without_local_status_guess():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "status: 'creating' as const" not in content
    assert "startCreatePolling(created.sandbox_id, created)" in content
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
    assert has_quote_style(content, "axios.get('/api/sandbox/providers'")
    assert "providerOptions.value = providers.map(" in content
    assert "defaultProviderId" in content
    assert (
        "providerOptions.value.find((option) => option.value === defaultProviderId)"
        in content
    )


def test_sandbox_management_page_does_not_show_legacy_provider_hint():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert not has_quote_style(content, "tm('create.providerHint')")


def test_sandbox_management_page_does_not_allow_configure_while_creating_or_restoring():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "case 'configure':")
    assert has_quote_style(
        content,
        "return status !== 'creating' && status !== 'restoring' && status !== 'stopping'",
    )


def test_sandbox_management_page_does_not_toast_running_after_create():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert not has_quote_style(content, "toast(tm('messages.createReady'))")


def test_sandbox_management_page_destroy_closes_dialog_before_backend_cleanup():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "const targetId = target.sandbox_id" in content
    assert "destroyDialog.value = false" in content
    assert "startDestroyPolling(targetId)" in content
    assert "const res = await axios.delete(sandboxApiPath(targetId)" in content
    assert not has_quote_style(content, "status: 'stopping'")
    assert "upsertSandboxRecord(stoppingRecord)" not in content
    assert "destroying" not in content
    assert (
        "const sandbox = res.data.data?.sandbox as SandboxRecord | undefined" in content
    )
    assert "upsertSandboxRecord(sandbox)" in content
    assert "void loadSandboxes({ silent: true })" in content
    assert "destroyQueued" not in content


def test_sandbox_management_page_polls_until_destroyed_sandbox_disappears():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "function startDestroyPolling" in content
    assert "pendingDestroySandboxes" in content
    assert (
        "const record = result.records.find((item) => item.sandbox_id === trackedSandboxId)"
        in content
    )
    assert "if (!record) {" in content
    assert "finishDestroyPolling(trackedSandboxId)" in content
    assert "removeSandboxRecord(sandboxId)" in content
    assert "startDestroyPolling(targetId)" in content


def test_sandbox_management_page_splits_running_into_busy_and_available_labels():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "return hasController(item) ? 'busy' : 'available'")


def test_sandbox_management_page_shows_controller_session_in_status_tooltip():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert 'v-tooltip v-if="item.controller_session_id" activator="parent"' in content
    assert "{{ item.controller_session_id }}" in content
    assert 'class="text-caption text-medium-emphasis mt-1"' not in content


def test_sandbox_management_page_confirms_dangerous_console_commands():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "function isDangerousConsoleCommand" in content
    assert has_quote_style(content, "window.confirm(tm('console.dangerConfirm'")
    assert "rm\\s+(?:-" in content
    assert "(?:--\\s+)?" in content


def test_sandbox_management_page_displays_console_cwd_relative_to_sandbox_home():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "if (cwd === '/workspace') return '~'")
    assert has_quote_style(
        content,
        "if (cwd.startsWith('/workspace/')) return `~${cwd.slice('/workspace'.length)}`",
    )
    assert "cwd.match(/^\\/home\\/[^/]+(.*)$/)" in content
    assert has_quote_style(content, "return suffix ? `~${suffix}` : '~'")


def test_sandbox_management_page_strips_console_cwd_markers_from_output():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "function stripConsoleCwdMarkers" in content
    assert "stripConsoleCwdMarkers(stdout)" in content
    assert "stripConsoleCwdMarkers(visibleStdout)" in content
    assert has_quote_style(content, "!line.includes('__ASTRBOT_CWD__')")


def test_sandbox_management_page_console_cwd_prefix_does_not_hide_failed_cd():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "? `cd ${quoteForShell(cwd)}; `" in content
    assert "? `cd ${quoteForShell(cwd)} && `" not in content


def test_sandbox_management_page_surfaces_unknown_status_key():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "tm('labels.unknownStatus', { status: key })")


def test_sandbox_management_page_localizes_max_sandbox_limit_errors():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )
    zh = (ROOT / "dashboard/src/i18n/locales/zh-CN/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    en = (ROOT / "dashboard/src/i18n/locales/en-US/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    ru = (ROOT / "dashboard/src/i18n/locales/ru-RU/features/sandbox.json").read_text(
        encoding="utf-8"
    )

    assert "function localizedSandboxError" in content
    assert "Sandbox limit reached" in content
    assert "messages.maxSandboxesReached" in content
    assert "maxSandboxesReached" in zh
    assert "maxSandboxesReached" in en
    assert "maxSandboxesReached" in ru


def test_sandbox_management_page_does_not_render_legacy_booter_type():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert "booter_type" not in content
    assert "showBooterTypeCaption" not in content
    assert "provider-summary" not in content


def test_sandbox_management_page_has_dedicated_capabilities_column():
    content = (ROOT / "dashboard/src/views/SandboxManagementPage.vue").read_text(
        encoding="utf-8"
    )

    assert has_quote_style(content, "key: 'capabilities'")
    assert 'v-for="capability in item.capabilities || []"' in content
    assert has_quote_style(content, "tm('headers.capabilities')")


def test_sandbox_i18n_uses_status_and_idle_labels():
    zh = (ROOT / "dashboard/src/i18n/locales/zh-CN/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    en = (ROOT / "dashboard/src/i18n/locales/en-US/features/sandbox.json").read_text(
        encoding="utf-8"
    )
    ru = (ROOT / "dashboard/src/i18n/locales/ru-RU/features/sandbox.json").read_text(
        encoding="utf-8"
    )

    assert '"status": "状态"' in zh
    assert '"available": "空闲"' in zh
    assert '"unknownStatus": "未知状态：{status}"' in zh
    assert '"status": "Status"' in en
    assert '"available": "Idle"' in en
    assert '"unknownStatus": "Unknown status: {status}"' in en
    assert '"dangerConfirm"' in zh
    assert '"dangerConfirm"' in en
    assert '"unknownStatus"' in ru
    assert '"dangerConfirm"' in ru
