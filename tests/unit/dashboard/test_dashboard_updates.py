from __future__ import annotations

import pytest

from tests.unit.dashboard.dashboard_lifecycle_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_check_update(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """Tests the update-check endpoint with mocked network calls."""
    test_client = DashboardTestClient(app)

    # Mock the release check.
    async def mock_check_update(*args, **kwargs):
        """Mock the updater returning no release."""
        return None

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "check_update",
        mock_check_update,
    )
    response = await test_client.get(
        "/api/v1/updates/check", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "success"
    assert data["data"]["has_new_version"] is False


@pytest.mark.asyncio
async def test_restart_core_rejects_desktop_managed_backend(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    restart_called = False

    async def mock_restart():
        nonlocal restart_called
        restart_called = True

    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setattr(core_lifecycle_td, "restart", mock_restart)

    response = await test_client.post(
        "/api/v1/system/restart",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.restart",
            resource_id="restart",
        ),
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == DESKTOP_MANAGED_RESTART_MESSAGE
    assert restart_called is False


@pytest.mark.slow
@pytest.mark.asyncio
async def test_do_update(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path_factory,
):
    test_client = DashboardTestClient(app)

    # Use a temporary path for the mock update to avoid side effects
    temp_release_dir = tmp_path_factory.mktemp("release")
    release_path = temp_release_dir / "astrbot"
    calls = []

    async def mock_download_core(*args, **kwargs):
        calls.append("download-core")
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"downloaded": 10, "total": 10, "percent": 1, "speed": 1})
        zip_path = kwargs["path"]
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("AstrBot-main/README.md", "core")
        return zip_path

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")
        os.makedirs(release_path, exist_ok=True)

    async def mock_pip_install(*args, **kwargs):
        """Mocks pip install to prevent actual installation."""
        return

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    app.state.services.updates.pip_install = mock_pip_install

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "test-progress"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["id"] == "test-progress"

    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "test-progress",
    )
    assert os.path.exists(release_path)
    assert calls[:2] == ["download-core", "apply-core"]

    assert progress_data["status"] == "ok"
    assert progress_data["data"]["status"] == "success"
    assert progress_data["data"]["overall_percent"] == 100


@pytest.mark.asyncio
async def test_do_update_does_not_apply_files_when_core_download_fails(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        calls.append("download-core")
        raise RuntimeError("core download failed")

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "atomic-fail"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "atomic-fail",
    )
    assert progress_data["data"]["status"] == "error"
    assert calls == ["download-core"]


@pytest.mark.asyncio
async def test_do_update_rejects_desktop_managed_backend(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        calls.append("download-core")

    async def mock_restart():
        calls.append("restart")

    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(core_lifecycle_td, "restart", mock_restart)

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "desktop-progress"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == DESKTOP_MANAGED_RESTART_MESSAGE
    assert calls == []


@pytest.mark.asyncio
async def test_do_update_does_not_apply_files_when_package_verification_fails(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args
        calls.append("download-core")
        zip_path = kwargs["path"]
        Path(zip_path).write_bytes(b"not a zip")
        return zip_path

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "invalid-zip"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "invalid-zip",
    )
    assert progress_data["data"]["status"] == "error"
    assert calls == ["download-core"]


@pytest.mark.asyncio
async def test_do_update_hides_internal_error_message_in_response_and_progress(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("secret stack trace")

    monkeypatch.setattr(
        app.state.services.updates.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "failed-progress"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert "secret stack trace" not in str(data)

    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "failed-progress",
    )

    assert progress_data["status"] == "ok"
    assert progress_data["data"]["status"] == "error"
    assert progress_data["data"]["message"] == "更新失败，请查看服务端日志。"
    assert "secret stack trace" not in str(progress_data)


@pytest.mark.asyncio
async def test_install_pip_package_returns_generic_error_message(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)

    async def mock_pip_install(*args, **kwargs):
        del args, kwargs
        raise PipInstallError("install failed", code=2)

    app.state.services.updates.pip_install = mock_pip_install

    response = await test_client.post(
        "/api/v1/pip/install",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.pip_install",
            resource_id="pip-install",
        ),
        json={"package": "demo-package"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "An internal error has occurred."


@pytest.mark.asyncio
async def test_neo_skills_routes(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    provider_settings = core_lifecycle_td.astrbot_config.setdefault(
        "provider_settings", {}
    )
    sandbox = provider_settings.setdefault("sandbox", {})
    sandbox["shipyard_neo_endpoint"] = "http://neo.test"
    sandbox["shipyard_neo_access_token"] = "neo-token"

    fake_shipyard_neo_module = SimpleNamespace(BayClient=_FakeNeoBayClient)
    monkeypatch.setitem(sys.modules, "shipyard_neo", fake_shipyard_neo_module)

    async def _fake_sync_release(self, client, **kwargs):
        _ = self, client, kwargs
        return SimpleNamespace(
            skill_key="neo.demo",
            local_skill_name="neo_demo",
            release_id="rel-2",
            candidate_id="cand-1",
            payload_ref="pref-1",
            map_path="data/skills/neo_skill_map.json",
            synced_at="2026-01-01T00:00:00Z",
        )

    async def _fake_sync_skills_to_active_sandboxes():
        return

    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.NeoSkillSyncManager.sync_release",
        _fake_sync_release,
    )
    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = DashboardTestClient(app)

    response = await test_client.get(
        "/api/v1/skills/neo/candidates", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "cand-1"

    response = await test_client.get(
        "/api/v1/skills/neo/releases", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "rel-1"

    response = await test_client.get(
        "/api/v1/skills/neo/payload?payload_ref=pref-1", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["payload_ref"] == "pref-1"

    response = await test_client.post(
        "/api/v1/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": True, "score": 0.95},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["candidate_id"] == "cand-1"
    assert data["data"]["passed"] is True

    response = await test_client.post(
        "/api/v1/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": "false", "score": 0.0},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["passed"] is False

    response = await test_client.post(
        "/api/v1/skills/neo/promote",
        json={"candidate_id": "cand-1", "stage": "stable"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["release"]["id"] == "rel-2"
    assert data["data"]["sync"]["local_skill_name"] == "neo_demo"

    response = await test_client.post(
        "/api/v1/skills/neo/rollback",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["rolled_back_release_id"] == "rel-2"

    response = await test_client.post(
        "/api/v1/skills/neo/sync",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["skill_key"] == "neo.demo"


@pytest.mark.asyncio
async def test_batch_upload_skills_returns_error_when_all_files_invalid(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"not-a-zip"),
                filename="invalid.txt",
                content_type="text/plain",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Upload failed for all 1 file(s)."


@pytest.mark.asyncio
async def test_batch_upload_skills_accepts_zip_files(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        _ = self, overwrite
        assert zip_path.endswith(".zip")
        assert skill_name_hint == "demo_skill"
        return "demo_skill"

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"fake-zip"),
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["message"] == "All 1 skill(s) uploaded successfully."
    assert data["data"]["total"] == 1
    assert data["data"]["succeeded"] == [
        {"filename": "demo_skill.zip", "name": "demo_skill"}
    ]
    assert data["data"]["failed"] == []


@pytest.mark.asyncio
async def test_batch_upload_skills_accepts_valid_skill_archive(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    skills_dir = tmp_path / "skills"
    temp_dir = tmp_path / "temp"
    data_dir.mkdir()
    skills_dir.mkdir()
    temp_dir.mkdir()

    async def _fake_sync_skills_to_active_sandboxes():
        return

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
        lambda: str(skills_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    test_skill_manager = SkillManager(
        skills_root=str(skills_dir),
        plugins_root=str(tmp_path / "plugins"),
    )
    monkeypatch.setattr(
        app.state.services.skills,
        "skill_manager",
        test_skill_manager,
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "demo_skill/SKILL.md",
            "---\nname: demo-skill\ndescription: Demo skill\n---\n",
        )
        zf.writestr("demo_skill/notes.txt", "hello")
        zf.writestr("__MACOSX/demo_skill/._SKILL.md", "")
        zf.writestr("__MACOSX/._demo_skill", "")
    archive.seek(0)

    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=archive,
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["succeeded"] == [
        {"filename": "demo_skill.zip", "name": "demo_skill"}
    ]
    assert data["data"]["failed"] == []
    assert (skills_dir / "demo_skill" / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_batch_upload_skills_partial_success(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        _ = self, overwrite
        assert skill_name_hint in {"ok_skill", "bad_skill"}
        if "ok_skill" in zip_path:
            return "ok_skill"
        raise RuntimeError("install failed")

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)

    boundary = "----AstrBotBatchBoundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="ok_skill.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + b"fake-zip-1\r\n"
        + (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="bad_skill.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + b"fake-zip-2\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    headers = dict(authenticated_header)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=headers,
        data=body,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["message"] == "Partial success: 1/2 skill(s) uploaded."
    assert data["data"]["total"] == 2
    assert data["data"]["succeeded"] == [
        {"filename": "ok_skill.zip", "name": "ok_skill"}
    ]
    assert data["data"]["failed"] == [
        {"filename": "bad_skill.zip", "error": "Skill upload failed"}
    ]


@pytest.mark.asyncio
async def test_batch_upload_skills_does_not_retry_internal_type_error(
    app: FastAPI,
    authenticated_header: dict,
    monkeypatch,
):
    calls = 0

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        nonlocal calls
        _ = self, zip_path, overwrite, skill_name_hint
        calls += 1
        raise TypeError("internal archive parsing failure")

    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"fake-zip"),
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert calls == 1
    assert data["data"]["failed"] == [
        {"filename": "demo_skill.zip", "error": "Skill upload failed"}
    ]


@pytest.mark.asyncio
async def test_skill_file_browser_and_editor_security(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo_skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\ndescription: Demo skill\n---\n# Demo\n",
        encoding="utf-8",
    )
    (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
    (skill_dir / "large.md").write_text("x" * (512 * 1024 + 1), encoding="utf-8")
    (skill_dir / "binary.md").write_bytes(b"\xff\xfe\x00")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    if hasattr(os, "symlink"):
        os.symlink(outside_file, skill_dir / "outside-link.txt")

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    test_skill_manager = SkillManager(
        skills_root=str(skills_root),
        plugins_root=str(tmp_path / "plugins"),
    )
    monkeypatch.setattr(
        app.state.services.skills,
        "skill_manager",
        test_skill_manager,
    )
    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = DashboardTestClient(app)

    list_response = await test_client.get(
        "/api/v1/skills/demo_skill/files",
        headers=authenticated_header,
    )
    list_data = await list_response.get_json()
    assert list_data["status"] == "ok"
    listed_paths = {item["path"] for item in list_data["data"]["entries"]}
    assert "SKILL.md" in listed_paths
    assert "outside-link.txt" not in listed_paths

    read_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/SKILL.md",
        headers=authenticated_header,
    )
    read_data = await read_response.get_json()
    assert read_data["status"] == "ok"
    assert "# Demo" in read_data["data"]["content"]

    update_response = await test_client.put(
        "/api/v1/skills/demo_skill/files/SKILL.md",
        content="# Updated\n",
        headers={**authenticated_header, "Content-Type": "text/plain; charset=utf-8"},
    )
    update_data = await update_response.get_json()
    assert update_data["status"] == "ok"
    assert skill_md.read_text(encoding="utf-8") == "# Updated\n"

    traversal_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/..%2Foutside.txt",
        headers=authenticated_header,
    )
    traversal_data = await traversal_response.get_json()
    assert traversal_data["status"] == "error"

    symlink_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/outside-link.txt",
        headers=authenticated_header,
    )
    symlink_data = await symlink_response.get_json()
    assert symlink_data["status"] == "error"

    large_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/large.md",
        headers=authenticated_header,
    )
    large_data = await large_response.get_json()
    assert large_data["status"] == "error"
    assert large_data["message"] == "File is too large"

    binary_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/binary.md",
        headers=authenticated_header,
    )
    binary_data = await binary_response.get_json()
    assert binary_data["status"] == "error"
    assert binary_data["message"] == "File is not valid UTF-8 text"
