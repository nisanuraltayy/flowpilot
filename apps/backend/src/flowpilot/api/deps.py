"""API dependency wiring — ADAPTER SEÇİMİ YALNIZ BURADA yapılır (ADR-009).

Bu dosya composition root'un izinli wiring noktasıdır; infrastructure
adapter'larını import edebilir. Router'lar YALNIZ buradaki dependency'leri ve
modüllerin application sınırlarını kullanır.

Kurallar:
- Import sırasında engine/DB bağlantısı OLUŞMAZ; her şey ilk istekte, lazy.
- API yalnız `DATABASE_URL` (flowpilot_app, BYPASSRLS'siz) ile bağlanır;
  admin/migrator URL'i ASLA kullanılmaz (ADR-006).
- Raw token yalnız bu katmanda yaşar; router'lara `CurrentActor` gider.
- Development-only actor header YOKTUR; kimlik yalnız doğrulanmış token'dan gelir.
- Testler bu dependency'leri `app.dependency_overrides` ile değiştirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.wiring import (
    SqlAlchemyApprovalDecisionUnitOfWork,
    SqlAlchemyApprovalRoleAssignmentListReadModel,
    SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork,
    SqlAlchemyBlockedApprovalTaskListReadModel,
    SqlAlchemyInvitationAcceptUnitOfWork,
    SqlAlchemyInvitationUnitOfWork,
    SqlAlchemyMemberListReadModel,
    SqlAlchemyMemberUpdateUnitOfWork,
    SqlAlchemyPurchaseRequestUnitOfWork,
    SqlAlchemyResolveBlockedTaskUnitOfWork,
    SqlAlchemyTaskInboxReadModel,
)
from flowpilot.config.settings import Settings
from flowpilot.modules.approval.application.blocked_task_handlers import (
    ListBlockedApprovalTasksHandler,
    ResolveBlockedApprovalTaskHandler,
)
from flowpilot.modules.approval.application.decide_handler import DecideApprovalTaskHandler
from flowpilot.modules.approval.application.ensure_assignments import (
    DefaultApproverResolver,
    EnsureDefaultApprovalRoleAssignments,
)
from flowpilot.modules.approval.application.role_assignment_handlers import (
    AssignApprovalRoleHandler,
    ListApprovalRoleAssignmentsHandler,
)
from flowpilot.modules.approval.infrastructure.persistence.repositories import (
    SqlAlchemyApprovalRoleAssignmentQuery,
)
from flowpilot.modules.approval.infrastructure.persistence.unit_of_work import (
    SqlAlchemyApprovalAssignmentUnitOfWork,
)
from flowpilot.modules.audit.infrastructure.persistence.timeline_query import (
    SqlAlchemyAuditTimelineQuery,
)
from flowpilot.modules.identity.application.auth import (
    AuthProviderPort,
    AuthProviderUnavailable,
    ExpiredAccessToken,
    InvalidAccessToken,
)
from flowpilot.modules.identity.application.ensure_user import (
    EnsureAuthenticatedUserHandler,
)
from flowpilot.modules.identity.infrastructure.persistence.unit_of_work import (
    SqlAlchemyIdentityUnitOfWork,
)
from flowpilot.modules.identity.infrastructure.persistence.user_directory import (
    SqlAlchemyUserDirectory,
)
from flowpilot.modules.identity.infrastructure.supabase_jwt import SupabaseJwtAuthAdapter
from flowpilot.modules.organization.application.handler import CreateOrganizationHandler
from flowpilot.modules.organization.application.invitation_accept import (
    AcceptInvitationHandler,
    PreviewInvitationHandler,
)
from flowpilot.modules.organization.application.invitation_handlers import (
    CreateInvitationHandler,
    ListPendingInvitationsHandler,
    RevokeInvitationHandler,
)
from flowpilot.modules.organization.application.member_handlers import (
    ListOrganizationMembersHandler,
    UpdateOrganizationMemberHandler,
)
from flowpilot.modules.organization.infrastructure.accept_url_builder import (
    SettingsInvitationAcceptUrlBuilder,
)
from flowpilot.modules.organization.infrastructure.persistence.invitation_preview_query import (
    SqlAlchemyInvitationPreviewQuery,
)
from flowpilot.modules.organization.infrastructure.persistence.invitation_query import (
    SqlAlchemyInvitationQuery,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_query import (
    SqlAlchemyMembershipQuery,
)
from flowpilot.modules.organization.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from flowpilot.modules.organization.infrastructure.token_generator import (
    SecretsInvitationTokenGenerator,
)
from flowpilot.modules.purchase_request.application.create_handler import (
    CreatePurchaseRequestHandler,
)
from flowpilot.modules.purchase_request.application.get_handler import GetPurchaseRequestHandler
from flowpilot.modules.purchase_request.infrastructure.persistence.read_query import (
    SqlAlchemyPurchaseRequestReadQuery,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentActor:
    """Doğrulanmış istek aktörü — yalnız internal FlowPilot UserId taşır."""

    user_id: UUID


def _unauthorized(detail: str) -> HTTPException:
    # Dışarı verilen mesaj token/provider detayı SIZDIRMAZ.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> sessionmaker[Session]:
    """App-scoped, lazy session factory (flowpilot_app rolü).

    Engine ilk ihtiyaçta oluşturulur (import'ta değil); gerçek bağlantı ancak
    bir session iş yaptığında açılır.
    """
    cached: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if cached is not None:
        return cached
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veritabani yapilandirmasi eksik.",
        )
    engine = create_engine(settings.require_database_url(), pool_pre_ping=True)
    factory = sessionmaker(bind=engine)
    request.app.state.session_factory = factory
    return factory


def get_auth_provider(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AuthProviderPort:
    """AuthProviderPort → SupabaseJwtAuthAdapter (production wiring).

    Supabase yapılandırılmamışsa local/test'te import ve health bozulmaz;
    auth gerektiren istek güvenli şekilde 503 alır. Staging/production'da
    eksik yapılandırma zaten `create_app` başlangıcında reddedilir.
    """
    cached: AuthProviderPort | None = getattr(request.app.state, "auth_provider", None)
    if cached is not None:
        return cached
    if settings.supabase_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kimlik dogrulama servisi yapilandirilmamis.",
        )
    adapter = SupabaseJwtAuthAdapter(
        supabase_url=settings.supabase_url,
        audience=settings.supabase_jwt_audience,
        allowed_algorithms=settings.supabase_allowed_algorithms,
        jwks_cache_seconds=settings.supabase_jwks_cache_seconds,
        jwks_timeout_seconds=settings.supabase_jwks_timeout_seconds,
    )
    request.app.state.auth_provider = adapter
    return adapter


def get_ensure_user_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> EnsureAuthenticatedUserHandler:
    return EnsureAuthenticatedUserHandler(
        unit_of_work_factory=lambda: SqlAlchemyIdentityUnitOfWork(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_create_organization_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> CreateOrganizationHandler:
    return CreateOrganizationHandler(
        unit_of_work=SqlAlchemyUnitOfWork(session_factory),
        user_directory=SqlAlchemyUserDirectory(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def _build_runtime_service(session_factory: sessionmaker[Session]) -> WorkflowRuntimeService:
    return WorkflowRuntimeService(
        unit_of_work_factory=lambda: SqlAlchemyWorkflowUnitOfWork(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_membership_query(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> SqlAlchemyMembershipQuery:
    return SqlAlchemyMembershipQuery(session_factory)


def get_create_invitation_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CreateInvitationHandler:
    return CreateInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        email_lookup=SqlAlchemyUserDirectory(session_factory),
        token_generator=SecretsInvitationTokenGenerator(),
        accept_url_builder=SettingsInvitationAcceptUrlBuilder(settings.frontend_base_url),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_list_pending_invitations_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ListPendingInvitationsHandler:
    return ListPendingInvitationsHandler(
        invitation_query=SqlAlchemyInvitationQuery(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        clock=SystemClock(),
    )


def get_revoke_invitation_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> RevokeInvitationHandler:
    return RevokeInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_preview_invitation_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> PreviewInvitationHandler:
    return PreviewInvitationHandler(
        preview_query=SqlAlchemyInvitationPreviewQuery(session_factory),
        clock=SystemClock(),
    )


def get_accept_invitation_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> AcceptInvitationHandler:
    return AcceptInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationAcceptUnitOfWork(session_factory),
        email_reader=SqlAlchemyUserDirectory(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_list_members_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ListOrganizationMembersHandler:
    return ListOrganizationMembersHandler(
        member_list_query=SqlAlchemyMemberListReadModel(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
    )


def get_update_member_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> UpdateOrganizationMemberHandler:
    return UpdateOrganizationMemberHandler(
        unit_of_work_factory=lambda: SqlAlchemyMemberUpdateUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_list_approval_roles_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ListApprovalRoleAssignmentsHandler:
    return ListApprovalRoleAssignmentsHandler(
        list_query=SqlAlchemyApprovalRoleAssignmentListReadModel(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
    )


def get_assign_approval_role_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> AssignApprovalRoleHandler:
    return AssignApprovalRoleHandler(
        unit_of_work_factory=lambda: SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork(
            session_factory
        ),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def _build_role_resolver(session_factory: sessionmaker[Session]) -> DefaultApproverResolver:
    """Approval rollerini owner'a idempotent atayan + aktif eşlemeyi çözen resolver.

    Cross-module compose burada (composition root) kurulur: approval provisioning UoW
    + organization membership contract + approval assignment query.
    """
    ensure = EnsureDefaultApprovalRoleAssignments(
        unit_of_work_factory=lambda: SqlAlchemyApprovalAssignmentUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    return DefaultApproverResolver(
        ensure=ensure,
        assignment_query=SqlAlchemyApprovalRoleAssignmentQuery(session_factory),
    )


def get_create_purchase_request_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> CreatePurchaseRequestHandler:
    runtime = _build_runtime_service(session_factory)
    return CreatePurchaseRequestHandler(
        unit_of_work_factory=lambda: SqlAlchemyPurchaseRequestUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        provisioning=runtime,
        runtime=runtime,
        role_resolver=_build_role_resolver(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_get_purchase_request_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> GetPurchaseRequestHandler:
    return GetPurchaseRequestHandler(
        read_query=SqlAlchemyPurchaseRequestReadQuery(session_factory),
        runtime=_build_runtime_service(session_factory),
    )


def get_decide_approval_task_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> DecideApprovalTaskHandler:
    """Onay kararı atomik use-case'i — runtime tx-port + compose UoW (tek transaction)."""
    return DecideApprovalTaskHandler(
        unit_of_work_factory=lambda: SqlAlchemyApprovalDecisionUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        runtime=_build_runtime_service(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_list_blocked_approval_tasks_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ListBlockedApprovalTasksHandler:
    return ListBlockedApprovalTasksHandler(
        list_query=SqlAlchemyBlockedApprovalTaskListReadModel(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
    )


def get_resolve_blocked_approval_task_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ResolveBlockedApprovalTaskHandler:
    return ResolveBlockedApprovalTaskHandler(
        unit_of_work_factory=lambda: SqlAlchemyResolveBlockedTaskUnitOfWork(session_factory),
        membership_query=SqlAlchemyMembershipQuery(session_factory),
        runtime=_build_runtime_service(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_task_inbox_query(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> SqlAlchemyTaskInboxReadModel:
    return SqlAlchemyTaskInboxReadModel(session_factory)


def get_purchase_request_read_query(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> SqlAlchemyPurchaseRequestReadQuery:
    return SqlAlchemyPurchaseRequestReadQuery(session_factory)


def get_audit_timeline_query(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> SqlAlchemyAuditTimelineQuery:
    return SqlAlchemyAuditTimelineQuery(session_factory)


def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    auth_provider: Annotated[AuthProviderPort, Depends(get_auth_provider)],
    ensure_user: Annotated[EnsureAuthenticatedUserHandler, Depends(get_ensure_user_handler)],
) -> CurrentActor:
    """Bearer token → doğrulanmış kimlik → internal user → CurrentActor.

    Token doğrulanmadan hiçbir DB işlemi yapılmaz; `ensure_user` yalnız
    doğrulama başarılıysa çağrılır.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Bearer access token gerekli.")

    try:
        identity = auth_provider.verify_token(credentials.credentials)
    except ExpiredAccessToken as exc:
        raise _unauthorized("Access token suresi dolmus.") from exc
    except InvalidAccessToken as exc:
        raise _unauthorized("Access token gecersiz.") from exc
    except AuthProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kimlik saglayicisina su anda erisilemiyor.",
        ) from exc

    user_id = ensure_user.handle(identity)
    return CurrentActor(user_id=user_id)
