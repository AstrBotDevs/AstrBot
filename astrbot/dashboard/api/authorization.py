"""Dashboard authorization bindings, step-up, and audit APIs."""

import inspect
import uuid
from collections.abc import Awaitable
from dataclasses import replace
from typing import Any, cast

from fastapi import APIRouter, Depends, Request

from astrbot.core.auth.models import (
    WEBCHAT_INSTANCE_TOOL_ACTIONS,
    AuthContext,
    AuthorizationValueError,
    Decision,
    Resource,
    Role,
    Subject,
    parse_canonical_session_resource,
    utc_now,
)
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    AuthorizationBindingBatchRevokeRequest,
    AuthorizationBindingRequest,
    AuthorizationStepUpRequest,
    DashboardAccountCreateRequest,
    DashboardAccountUpdateRequest,
    WebChatStepUpRequest,
)

from .auth import object_resource, require_dashboard_session_principal

router = APIRouter(prefix="/authorization", tags=["Authorization"])


def _service(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    services = getattr(runtime, "services", None)
    authorization = getattr(services, "authorization", None)
    if authorization is None:
        raise ApiError("Authorization unavailable", status_code=503)
    return authorization


def _auth_service(request: Request):
    return request.app.state.services.auth


def _principal_context(request: Request, principal) -> tuple[Subject, AuthContext]:
    if principal.account_subject is None:
        raise ApiError("Dashboard account is unavailable", status_code=401)
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
        message_type=context.message_type,
        platform_member_role=context.platform_member_role,
        platform_role_source=context.platform_role_source,
        platform_role_expires_at=context.platform_role_expires_at,
        authenticated=context.authenticated,
        principal_subject_id=context.principal_subject_id,
        api_scopes=context.api_scopes,
        auth_strength=context.auth_strength,
        authenticated_at=context.authenticated_at,
        step_up_token=token,
        origin_session_resource_id=context.origin_session_resource_id,
        caller_declared_username=context.caller_declared_username,
        metadata=dict(context.metadata),
    )


async def _webchat_step_up_target(
    request: Request,
    principal,
    session_id: str,
) -> tuple[Subject, AuthContext, Resource]:
    """Reconstruct the trusted WebChat session/config target server-side."""

    if principal.account_subject is None:
        raise ApiError("Dashboard account is unavailable", status_code=401)
    chat_service = getattr(request.app.state.services, "chat", None)
    chat_db = getattr(chat_service, "db", None) or getattr(
        request.app.state, "db", None
    )
    get_session = getattr(chat_db, "get_platform_session_by_id", None)
    session = None
    if callable(get_session):
        loaded = get_session(session_id)
        session = (
            await cast(Awaitable[Any], loaded)
            if inspect.isawaitable(loaded)
            else loaded
        )
    create_session = getattr(chat_db, "create_platform_session", None)
    if session is None and callable(create_session):
        # The chat UI can have a route for a freshly allocated conversation
        # before the first message persists its platform session.  Establish
        # the same Dashboard-owned session that ChatService would create for
        # the first send, but never adopt an existing session from another
        # account.  UUID validation keeps this recovery path scoped to normal
        # WebChat session identifiers rather than arbitrary database keys.
        try:
            if str(uuid.UUID(session_id)) != session_id:
                raise ValueError("non-canonical session id")
        except ValueError, AttributeError, TypeError:
            session = None
        else:
            try:
                created = create_session(
                    creator=principal.username,
                    platform_id="webchat",
                    session_id=session_id,
                )
                session = (
                    await cast(Awaitable[Any], created)
                    if inspect.isawaitable(created)
                    else created
                )
            except Exception:
                # A concurrent first message may have won the insert race.
                # Re-read and apply the ownership check below; do not turn a
                # collision into an account-adoption opportunity.
                if callable(get_session):
                    reloaded = get_session(session_id)
                    session = (
                        await cast(Awaitable[Any], reloaded)
                        if inspect.isawaitable(reloaded)
                        else reloaded
                    )
    if (
        session is None
        or getattr(session, "platform_id", None) != "webchat"
        or getattr(session, "creator", None) != principal.username
    ):
        raise ApiError("Authorization denied", status_code=403)
    umo = f"webchat:FriendMessage:webchat!{principal.username}!{session_id}"
    router = getattr(
        getattr(request.app.state, "runtime", None), "umop_config_router", None
    )
    config_id = router.get_conf_id_for_umop(umo) if router is not None else None
    config_id = config_id or "default"
    resource = Resource.session(config_id, umo)
    subject = principal.account_subject
    context = AuthContext(
        subject=subject,
        source="webchat",
        config_id=config_id,
        platform="webchat",
        message_type="FriendMessage",
        # WebChatMessageEvent currently carries the neutral compatibility role
        # ``member``; bind issuance to that trusted event fact so the proof
        # digest can be consumed by the eventual tool call.
        platform_member_role="member",
        platform_role_source="none",
        authenticated=True,
        principal_subject_id=subject.id,
        auth_strength=principal.auth_strength,
        authenticated_at=principal.issued_at,
        origin_session_resource_id=resource.id,
        caller_declared_username=principal.username,
        metadata={"dashboard_session_id": principal.sid},
    )
    return subject, context, resource


async def _authorize_identity_read(
    request: Request,
    *,
    subject: Subject,
    context: AuthContext,
    resource_name: str,
) -> tuple[Decision, set[str] | None]:
    """Authorize global readers or infer their instance-scoped bindings."""

    authorization = _service(request)
    unscoped_resource = Resource.named("identity", resource_name)
    unscoped = await authorization.authorize(
        subject,
        "identity.read",
        unscoped_resource,
        context,
    )
    if unscoped.allowed and unscoped.effective_role in {Role.ROOT, Role.OPERATOR}:
        return unscoped, None

    own_bindings = await authorization.list_bindings(subject_id=subject.id)
    config_ids = {
        item.config_id
        for item in own_bindings
        if (
            item.role == Role.INSTANCE_OPERATOR.value
            and item.scope_type == "instance"
            and item.config_id
            and (item.expires_at is None or item.expires_at > utc_now())
        )
    }
    if not config_ids:
        raise ApiError("Authorization denied", status_code=403)

    allowed_config_ids: set[str] = set()
    first_decision: Decision | None = None
    for config_id in sorted(config_ids):
        scoped_context = replace(context, config_id=config_id)
        scoped_resource = Resource.named(
            "identity",
            resource_name,
            config_id=config_id,
        )
        decision = await authorization.authorize(
            subject,
            "identity.read",
            scoped_resource,
            scoped_context,
        )
        if decision.allowed:
            allowed_config_ids.add(config_id)
            first_decision = first_decision or decision

    if first_decision is None:
        raise ApiError("Authorization denied", status_code=403)
    return first_decision, allowed_config_ids


async def _require(
    request: Request,
    *,
    subject: Subject,
    context: AuthContext,
    action: str,
    resource: Resource,
) -> Decision:
    decision = await _service(request).authorize(subject, action, resource, context)
    if not decision.allowed:
        raise ApiError("Authorization denied", status_code=403)
    return decision


def _resource(payload) -> Resource:
    """Build a canonical, step-up-safe resource from Dashboard input."""

    try:
        if payload.resource_type == "session":
            try:
                config_id, umo = parse_canonical_session_resource(payload.resource_id)
            except AuthorizationValueError:
                if not payload.config_id:
                    raise ApiError(
                        "config_id is required for session resources", status_code=400
                    )
                return Resource.session(payload.config_id, payload.resource_id)
            if payload.config_id and payload.config_id != config_id:
                raise ApiError("Session resource config mismatch", status_code=400)
            return Resource.session(config_id, umo)
        if payload.resource_type == "instance":
            if not payload.config_id or payload.resource_id != payload.config_id:
                raise ApiError("Invalid instance resource", status_code=400)
            return Resource.instance(payload.config_id)
        if payload.resource_type == "bot":
            # Bot routes hash object identifiers before authorization so raw
            # platform IDs never become resource keys. Keep step-up issuance
            # on the same canonical resource as bot mutation requests.
            if payload.resource_id == "collection":
                return Resource.named("bot", "collection", config_id=payload.config_id)
            return object_resource(
                "bot", payload.resource_id, config_id=payload.config_id
            )
        if payload.resource_type == "filesystem":
            # Relative data paths may contain Unicode, spaces and dots.  Their
            # authorization identity must therefore use the opaque helper,
            # matching the data-files routes rather than Resource.named().
            if payload.resource_id == "collection":
                return Resource.named("filesystem", "collection")
            return object_resource("filesystem", payload.resource_id)
        return Resource.named(
            payload.resource_type, payload.resource_id, config_id=payload.config_id
        )
    except AuthorizationValueError as exc:
        raise ApiError("Invalid authorization resource", status_code=400) from exc


@router.get("/role-bindings")
async def list_role_bindings(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    _decision, config_ids = await _authorize_identity_read(
        request,
        subject=subject,
        context=context,
        resource_name="bindings",
    )
    if config_ids is None:
        bindings = await _service(request).list_bindings()
    else:
        bindings = []
        for config_id in sorted(config_ids):
            bindings.extend(await _service(request).list_bindings(config_id=config_id))
        bindings = [item for item in bindings if item.scope_type != "global"]
    return ok([item.model_dump() for item in bindings])


@router.post("/role-bindings")
async def grant_role_binding(
    payload: AuthorizationBindingRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    actor, context = _principal_context(request, principal)
    try:
        role = Role(payload.role)
        binding = await _service(request).grant_binding(
            actor=actor,
            subject_id=payload.subject_id,
            role=role,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            config_id=payload.config_id,
            expires_at=payload.expires_at,
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
            actor=actor,
            binding_id=binding_id,
            context=_step_up_context(context, request.headers.get("X-AstrBot-Step-Up")),
        )
    except (ValueError, PermissionError) as exc:
        raise ApiError("Authorization denied", status_code=403) from exc
    if not revoked:
        raise ApiError("Binding not found", status_code=404)
    return ok()


@router.post("/role-bindings/batch-revoke/step-up")
async def issue_batch_revoke_step_up(
    payload: AuthorizationBindingBatchRevokeRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    """Verify a factor and bind one credential to this exact revoke batch."""

    subject, context = _principal_context(request, principal)
    try:
        resource = await _service(request).binding_revocation_batch_resource(
            payload.binding_ids
        )
    except AuthorizationValueError as exc:
        raise ApiError("Binding batch is unavailable", status_code=400) from exc
    decision = await _service(request).authorize(
        subject, "identity.manage", resource, context
    )
    if decision.reason != "step_up_required":
        status_code = 403 if not decision.allowed else 400
        raise ApiError("Authorization denied", status_code=status_code)
    method = await _auth_service(request).verify_step_up_factor(
        account_id=principal.account_id or "",
        password=payload.password,
        code=payload.code,
    )
    if method is None:
        _service(request).record_step_up_failure(
            subject=subject,
            action="identity.manage",
            resource=resource,
            context=context,
        )
        raise ApiError("Reauthentication required", status_code=401)
    credential_id, token = await _service(request).issue_step_up(
        subject=subject,
        dashboard_session_id=principal.sid,
        action="identity.manage",
        resource=resource,
        context=context,
        verified_method=method,
    )
    return ok({"step_up_id": credential_id, "token": token})


@router.post("/role-bindings/batch-revoke")
async def revoke_role_bindings(
    payload: AuthorizationBindingBatchRevokeRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    actor, context = _principal_context(request, principal)
    try:
        revoked_count = await _service(request).revoke_bindings(
            actor=actor,
            binding_ids=payload.binding_ids,
            context=_step_up_context(context, request.headers.get("X-AstrBot-Step-Up")),
        )
    except (AuthorizationValueError, PermissionError, ValueError) as exc:
        raise ApiError("Authorization denied", status_code=403) from exc
    return ok({"revoked_count": revoked_count})


@router.post("/step-up")
async def issue_step_up(
    payload: AuthorizationStepUpRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    resource = _resource(payload)
    if resource.config_id is not None:
        # Resource mutations use the resource's config scope as an explicit
        # authorization context fact. Keep issuance and consumption digests
        # identical for config-scoped Dashboard actions.
        context = replace(context, config_id=resource.config_id)
    decision = await _service(request).authorize(
        subject, payload.action, resource, context
    )
    if decision.reason != "step_up_required":
        status_code = 403 if not decision.allowed else 400
        raise ApiError("Authorization denied", status_code=status_code)
    method = await _auth_service(request).verify_step_up_factor(
        account_id=principal.account_id or "",
        password=payload.password,
        code=payload.code,
    )
    if method is None:
        _service(request).record_step_up_failure(
            subject=subject,
            action=payload.action,
            resource=resource,
            context=context,
        )
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


@router.post("/webchat-step-up")
async def issue_webchat_step_up(
    payload: WebChatStepUpRequest,
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    """Issue one exact-action token per allowed WebChat tool action.

    The request names only a session.  The account, Dashboard sid, canonical
    UMO, config route, role, and action set are reconstructed on the server.
    Password/TOTP never cross the WebSocket or enter a chat message.
    """

    subject, context, resource = await _webchat_step_up_target(
        request, principal, payload.session_id
    )
    authorization = _service(request)
    actions = tuple(sorted(WEBCHAT_INSTANCE_TOOL_ACTIONS))
    decisions = [
        await authorization.authorize(subject, action, resource, context)
        for action in actions
    ]
    if any(decision.reason == "role_scope_denied" for decision in decisions):
        raise ApiError("Authorization denied", status_code=403)
    if not all(decision.reason == "step_up_required" for decision in decisions):
        raise ApiError("Authorization denied", status_code=403)
    method = await _auth_service(request).verify_step_up_factor(
        account_id=principal.account_id or "",
        password=payload.password,
        code=payload.code,
    )
    if method is None:
        authorization.record_step_up_failure(
            subject=subject,
            action=actions[0],
            resource=resource,
            context=context,
        )
        raise ApiError("Reauthentication required", status_code=401)

    tokens: dict[str, str] = {}
    for action in actions:
        _credential_id, token = await authorization.issue_step_up(
            subject=subject,
            dashboard_session_id=principal.sid,
            action=action,
            resource=resource,
            context=context,
            verified_method=method,
        )
        tokens[action] = token
    return ok({"tokens": tokens, "expires_in": 300})


@router.get("/audit")
async def list_authorization_audit(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    _decision, config_ids = await _authorize_identity_read(
        request,
        subject=subject,
        context=context,
        resource_name="audit",
    )
    records = await _service(request).list_audit()
    if config_ids is not None:
        records = [item for item in records if item.config_id in config_ids]
    return ok([item.model_dump() for item in records])


@router.get("/accounts")
async def list_dashboard_accounts(
    request: Request,
    principal=Depends(require_dashboard_session_principal),
):
    subject, context = _principal_context(request, principal)
    decision = await _require(
        request,
        subject=subject,
        context=context,
        action="identity.read",
        resource=Resource.named("dashboard-account", "accounts"),
    )
    if decision.effective_role not in {Role.OPERATOR, Role.ROOT}:
        raise ApiError("Authorization denied", status_code=403)
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
    action = (
        "identity.root.write" if payload.role == "root" else "identity.operator.write"
    )
    action_context = _step_up_context(context, request.headers.get("X-AstrBot-Step-Up"))
    decision = await _require(
        request,
        subject=subject,
        context=action_context,
        action=action,
        resource=Resource.named("dashboard-account", payload.username),
    )
    try:
        account, binding = await _auth_service(
            request
        ).create_dashboard_account_with_role(
            username=payload.username,
            password=payload.password,
            created_by=subject.id,
            role=Role(payload.role),
            actor=subject,
            audit_context=action_context,
            audit_decision=decision,
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
    decision = await _require(
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
            actor=subject,
            audit_context=action_context,
            audit_decision=decision,
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
