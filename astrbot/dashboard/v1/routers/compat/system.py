from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import (
    get_bridge,
    require_config_scope,
    require_system_scope,
)
from .common import (
    json_or_empty as _json_or_empty,
)

router = APIRouter(tags=["System"])


@router.get("/stats")
async def get_stats(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/get"
    )


@router.get("/stats/provider-tokens")
async def provider_tokens(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/provider-tokens"
    )


@router.get("/stats/version")
async def version(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/version"
    )


@router.get("/stats/first-notice")
async def first_notice(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/first-notice"
    )


@router.post("/stats/ghproxy/test")
async def test_ghproxy_connection(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/stat/test-ghproxy-connection",
    )


@router.get("/changelogs")
async def list_changelog_versions(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/changelog/list"
    )


@router.get("/changelogs/{version}")
async def get_changelog(
    version: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/stat/changelog",
        query={"version": version},
    )


@router.get("/stats/start-time")
async def start_time(
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, None, method="GET", target_path="/api/stat/start-time"
    )


@router.get("/stats/storage")
async def storage_status(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/stat/storage"
    )


@router.post("/stats/storage/cleanup")
async def cleanup_storage(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/stat/storage/cleanup"
    )


@router.post("/system/restart")
async def restart_system(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/stat/restart-core"
    )


@router.get("/logs/history")
async def log_history(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/log-history"
    )


@router.get("/logs/live")
async def live_logs(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/live-log"
    )


@router.get("/cron/jobs")
async def list_cron_jobs(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/cron/jobs"
    )


@router.post("/cron/jobs")
async def create_cron_job(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/cron/jobs"
    )


@router.patch("/cron/jobs/{job_id}")
async def update_cron_job(
    job_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="PATCH",
        target_path=f"/api/cron/jobs/{job_id}",
    )


@router.delete("/cron/jobs/{job_id}")
async def delete_cron_job(
    job_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="DELETE",
        target_path=f"/api/cron/jobs/{job_id}",
    )


@router.post("/cron/jobs/{job_id}/run")
async def run_cron_job(
    job_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path=f"/api/cron/jobs/{job_id}/run",
    )


@router.get("/trace/settings")
async def get_trace_settings(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/trace/settings"
    )


@router.put("/trace/settings")
async def update_trace_settings(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/trace/settings"
    )


@router.get("/updates/check")
async def check_updates(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/update/check"
    )


@router.get("/updates/releases")
async def update_releases(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/update/releases"
    )


@router.get("/updates/progress/{task_id}")
async def update_progress(
    task_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/update/progress",
        query={"id": task_id},
    )


@router.post("/updates/core")
async def update_core(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/update/do"
    )


@router.post("/updates/dashboard")
async def update_dashboard(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/update/dashboard"
    )


@router.post("/pip/install")
async def install_pip_package(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/update/pip-install"
    )


@router.post("/migrations")
async def run_migration(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/update/migration"
    )


@router.get("/subagents/config")
async def get_subagent_config(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/subagent/config"
    )


@router.put("/subagents/config")
async def update_subagent_config(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/subagent/config"
    )


@router.get("/subagents/available-tools")
async def get_subagent_tools(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/subagent/available-tools"
    )


@router.get("/backups")
async def list_backups(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/backup/list"
    )


@router.post("/backups")
async def export_backup(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/export"
    )


@router.post("/backups/upload")
async def upload_backup(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/upload"
    )


@router.post("/backups/upload/init")
async def init_backup_upload(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/upload/init"
    )


@router.post("/backups/upload/chunk")
async def upload_backup_chunk(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/upload/chunk"
    )


@router.post("/backups/upload/complete")
async def complete_backup_upload(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/upload/complete"
    )


@router.post("/backups/upload/abort")
async def abort_backup_upload(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/backup/upload/abort"
    )


@router.get("/backups/tasks/{task_id}")
async def get_backup_progress(
    task_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/backup/progress",
        query={"task_id": task_id},
    )


@router.get("/backups/{filename}")
async def download_backup(
    filename: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/backup/download",
        query={"filename": filename},
    )


@router.patch("/backups/{filename}")
async def rename_backup(
    filename: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/backup/rename",
        json_body={"filename": filename, **body},
    )


@router.delete("/backups/{filename}")
async def delete_backup(
    filename: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/backup/delete",
        json_body={"filename": filename},
    )


@router.post("/backups/{filename}/check")
async def check_backup(
    filename: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/backup/check",
        json_body={"filename": filename, **body},
    )


@router.post("/backups/{filename}/import")
async def import_backup(
    filename: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/backup/import",
        json_body={"filename": filename, **body},
    )


@router.get("/t2i/templates")
async def list_t2i_templates(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/t2i/templates"
    )


@router.post("/t2i/templates")
async def create_t2i_template(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/t2i/templates/create"
    )


@router.get("/t2i/templates/active")
async def get_active_t2i_template(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/t2i/templates/active"
    )


@router.put("/t2i/templates/active")
async def set_active_t2i_template(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/t2i/templates/set_active"
    )


@router.post("/t2i/templates/default/reset")
async def reset_default_t2i_template(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/t2i/templates/reset_default"
    )


@router.get("/t2i/templates/{name}")
async def get_t2i_template(
    name: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path=f"/api/t2i/templates/{name}",
    )


@router.put("/t2i/templates/{name}")
async def update_t2i_template(
    name: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="PUT",
        target_path=f"/api/t2i/templates/{name}",
    )


@router.delete("/t2i/templates/{name}")
async def delete_t2i_template(
    name: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="DELETE",
        target_path=f"/api/t2i/templates/{name}",
    )
