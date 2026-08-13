"""Dashboard authorization bindings, step-up, elevation, and audit APIs."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    AuthorizationBindingRequest,
    AuthorizationElevationApprovalRequest,
    AuthorizationElevationRequest,
    AuthorizationStepUpRequest,
    DashboardAccountCreateRequest,
    DashboardAccountUpdateRequest,
)

from .auth import require_dashboard_session_principal

router = APIRouter(prefix="/authorization", tags=["Authorization"])


def _service(request: Request):
    return request.app.state.runtime.services.authorization


def _auth_service(request: Request):
    return request.app.state.services.auth


def _principal_context(request: Request, principal) -> tuple[Subject, AuthContext]:
    if principal.account_subject is None:
        raise ApiError("Dashboard account migration required", status_code=401)
    subject = principal.account_subject
    context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id=None,
        authenticated=True,
        auth_strength=principal.auth_strength,
        authenticated_at=principal.issued_at,
        principal_subject_id=subject.id,
        metadata={"dashboard_session_id": principal.sid},
    )
    return subject, context


def _step_up_context(context: AuthContext, token: str | None) -> AuthContext:
    """Bind a one-time step-up token to this exact control-plane request."""

    return AuthContext(
        subject=context.subject,
        source=context.source,
        request_id=context.request_id,
        config_id=context.config_id,
        platform=context.platform,
        authenticated=context.authenticated,
        principal_subject_id=context.principal_subject_id,
        auth_strength=context.auth_strength,
        authenticated_at=context.authenticated_at,
        step_up_token=token,
        metadata=dict(context.metadata),
    )


async def _require(
    request: Request,
    *,
    subject: Subject,
    context: AuthContext,
    action: str,
    resource: Resource,
) -> None:
    decision = await _service(request).authorize(subject, action, resource, context)
    if not decision.allowed:
        raise ApiError("Authorization denied", status_code=403)


def _resource(payload) -> Resource:
    if payload.resource_type == "session":
        if not payload.config_id:
            raise ApiError(
                "config_id is required for session resources", status_code=400
            )
        return Resource.session(payload.config_id, payload.resource_id)
    return Resource.named(
        payload.resource_type, payload.resource_id, config_id=payload.config_id
    )


@router.get("/role-bindings")
async def list_role_bindings(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    await _require(
        request,
        subject=subject,
        context=context,
        action="identity.read",
        resource=Resource.named("identity", "bindings"),
    )
    return ok([item.model_dump() for item in await _service(request).list_bindings()])


@router.post("/role-bindings")
async def grant_role_binding(
    payload: AuthorizationBindingRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    actor, context = _principal_context(request, principal)
    try:
        role = Role(payload.role)
        expires_at = (
            datetime.fromisoformat(payload.expires_at) if payload.expires_at else None
        )
        binding = await _service(request).grant_binding(
            actor=actor,
            subject_id=payload.subject_id,
            role=role,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            config_id=payload.config_id,
            expires_at=expires_at,
            context=_step_up_context(context, request.headers.get("X-AstrBot-Step-Up")),
        )
    except (ValueError, PermissionError) as exc:
        raise ApiError("Authorization denied", status_code=403) from exc
    return ok(binding.model_dump())


@router.post("/role-bindings/{binding_id}/revoke")
async def revoke_role_binding(
    binding_id: str,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    actor, context = _principal_context(request, principal)
    try:
        revoked = await _service(request).revoke_binding(
            actor=actor, binding_id=binding_id
            , context=_step_up_context(context, request.headers.get("X-AstrBot-Step-Up"))
        )
    except (ValueError, PermissionError) as exc:
        raise ApiError("Authorization denied", status_code=403) from exc
    if not revoked:
        raise ApiError("Binding not found", status_code=404)
    return ok()


@router.post("/step-up")
async def issue_step_up(
    payload: AuthorizationStepUpRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    resource = _resource(payload)
    decision = await _service(request).authorize(
        subject, payload.action, resource, context
    )
    if decision.reason not in {"step_up_required", "elevation_required"}:
        raise ApiError("Step-up is not required for this action", status_code=400)
    method = await _auth_service(request).verify_step_up_factor(
        account_id=principal.account_id or "",
        password=payload.password,
        code=payload.code,
    )
    if method is None:
        raise ApiError("Reauthentication required", status_code=401)
    credential_id, token = await _service(request).issue_step_up(
        subject=subject,
        dashboard_session_id=principal.sid,
        action=payload.action,
        resource=resource,
        context=context,
        verified_method=method,
    )
    return ok({"step_up_id": credential_id, "token": token})


@router.get("/audit")
async def list_authorization_audit(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    await _require(
        request,
        subject=subject,
        context=context,
        action="identity.read",
        resource=Resource.named("identity", "audit"),
    )
    records = await _service(request).list_audit()
    return ok([item.model_dump() for item in records])


@router.get("/accounts")
async def list_dashboard_accounts(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    await _require(
        request,
        subject=subject,
        context=context,
        action="identity.read",
        resource=Resource.named("dashboard-account", "accounts"),
    )
    accounts = await _auth_service(request).list_dashboard_accounts()
    return ok(
        [
            {
                "account_id": account.account_id,
                "username": account.username,
                "is_active": account.is_active,
                "created_by": account.created_by,
                "created_at": account.created_at,
                "last_login_at": account.last_login_at,
            }
            for account in accounts
        ]
    )


@router.post("/accounts")
async def create_dashboard_account(
    payload: DashboardAccountCreateRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    action = "identity.root.write" if payload.role == "root" else "identity.operator.write"
    action_context = _step_up_context(context, request.headers.get("X-AstrBot-Step-Up"))
    await _require(
        request,
        subject=subject,
        context=action_context,
        action=action,
        resource=Resource.named("dashboard-account", payload.username),
    )
    try:
        account, binding = await _auth_service(request).create_dashboard_account_with_role(
            username=payload.username,
            password=payload.password,
            created_by=subject.id,
            role=Role(payload.role),
        )
    except ValueError as exc:
        raise ApiError("Invalid account request", status_code=400) from exc
    return ok(
        {
            "account_id": account.account_id,
            "username": account.username,
            "role_binding_id": binding.binding_id,
        }
    )


@router.patch("/accounts/{account_id}")
async def update_dashboard_account(
    account_id: str,
    payload: DashboardAccountUpdateRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    action_context = _step_up_context(context, request.headers.get("X-AstrBot-Step-Up"))
    await _require(
        request,
        subject=subject,
        context=action_context,
        action="dashboard.account.manage",
        resource=Resource.named("dashboard-account", account_id),
    )
    try:
        account = await _auth_service(request).update_dashboard_account(
            account_id=account_id,
            username=payload.username,
            password=payload.password,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise ApiError("Invalid account request", status_code=400) from exc
    if account is None:
        raise ApiError("Account not found", status_code=404)
    return ok(
        {
            "account_id": account.account_id,
            "username": account.username,
            "is_active": account.is_active,
        }
    )


@router.post("/elevation-requests")
async def request_elevation(
    payload: AuthorizationElevationRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    resource = _resource(payload)
    decision = await _service(request).authorize(
        subject, payload.action, resource, context
    )
    if not decision.requires_elevation:
        raise ApiError("Elevation is not required or available", status_code=403)
    request_id, nonce = await _service(request).request_elevation(
        decision, context, approval_channel=payload.approval_channel
    )
    return ok({"request_id": request_id, "nonce": nonce})


@router.post("/elevation-requests/{request_id}/approve")
async def approve_elevation(
    request_id: str,
    payload: AuthorizationElevationApprovalRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    approver, context = _principal_context(request, principal)
    approved = await _service(request).approve_elevation(
        request_id=request_id,
        nonce=payload.nonce,
        approver=approver,
        context=context,
    )
    if not approved:
        raise ApiError("Elevation approval denied", status_code=403)
    return ok()
