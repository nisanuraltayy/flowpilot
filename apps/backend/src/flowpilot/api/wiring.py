"""Composition root wiring — CROSS-MODULE compose adapter'ları YALNIZ burada.

Bu bir wiring dosyasıdır (ADR-009 §2b; import-boundary muafiyeti). İki modülün
infrastructure adapter'larını TEK SQLAlchemy session'ı üzerinde birleştirir; böylece
Purchase Request + workflow instance start AYNI transaction'da commit edilir. İş
mantığı İÇERMEZ — yalnız adapter kompozisyonu.
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.ports import ApprovalDecisionRepository
from flowpilot.modules.approval.application.role_assignment_dto import (
    ApprovalRoleAssignmentView,
    TargetMembershipInfo,
)
from flowpilot.modules.approval.application.role_assignment_ports import (
    ApprovalRoleAssignmentManagementRepository,
    TargetMembershipReader,
)
from flowpilot.modules.approval.infrastructure.persistence.repositories import (
    SqlAlchemyApprovalDecisionRepository,
)
from flowpilot.modules.approval.infrastructure.persistence.role_assignment_management_repository import (  # noqa: E501
    SqlAlchemyApprovalRoleAssignmentManagementRepository,
)
from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.audit.infrastructure.persistence.writer import SqlAlchemyAuditWriter
from flowpilot.modules.organization.application.invitation_ports import (
    AcceptIdempotencyRepository,
    InvitationRepository,
    MembershipWriteRepository,
)
from flowpilot.modules.organization.application.member_dto import MemberView
from flowpilot.modules.organization.application.member_ports import (
    ApprovalResponsibilityQuery,
    MembershipManagementRepository,
)
from flowpilot.modules.organization.infrastructure.persistence.accept_idempotency_repository import (  # noqa: E501
    SqlAlchemyAcceptIdempotencyRepository,
)
from flowpilot.modules.organization.infrastructure.persistence.invitation_repository import (
    SqlAlchemyInvitationRepository,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_management_repository import (  # noqa: E501
    SqlAlchemyMembershipManagementRepository,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_repository import (
    SqlAlchemyMembershipWriteRepository,
)
from flowpilot.modules.purchase_request.application.dto import InboxItem
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestRepository
from flowpilot.modules.purchase_request.infrastructure.persistence.repository import (
    SqlAlchemyPurchaseRequestRepository,
)
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)


class SqlAlchemyPurchaseRequestUnitOfWork(SqlAlchemyWorkflowUnitOfWork):
    """workflow_runtime UoW + purchase_requests repo — TEK session, TEK transaction.

    `SqlAlchemyWorkflowUnitOfWork`'ü genişletir (tüm runtime repo'ları aynı session'da
    kurulur) ve purchase_requests repo'sunu EKLER. Böylece iki modülün yazımları tek
    commit/rollback ile atomiktir ve tek tenant context altındadır.
    """

    purchase_requests: PurchaseRequestRepository
    audit: AuditWriterPort

    def __enter__(self) -> SqlAlchemyPurchaseRequestUnitOfWork:
        super().__enter__()
        session = self._require_session()
        self.purchase_requests = SqlAlchemyPurchaseRequestRepository(session)
        self.audit = SqlAlchemyAuditWriter(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)


def purchase_request_uow_factory(
    session_factory: sessionmaker[Session],
) -> SqlAlchemyPurchaseRequestUnitOfWork:
    return SqlAlchemyPurchaseRequestUnitOfWork(session_factory)


class SqlAlchemyApprovalDecisionUnitOfWork(SqlAlchemyPurchaseRequestUnitOfWork):
    """runtime UoW + purchase_requests + approval_decisions + audit — TEK transaction.

    Onay kararı akışının cross-module ATOMİKLİĞİNİ sağlar: runtime task transition +
    PR status + ApprovalDecision + audit AYNI session/transaction'da commit edilir.
    """

    approval_decisions: ApprovalDecisionRepository
    # `audit` parent'ta (SqlAlchemyPurchaseRequestUnitOfWork) zaten kurulur — miras alınır.

    def __enter__(self) -> SqlAlchemyApprovalDecisionUnitOfWork:
        super().__enter__()
        session = self._require_session()
        self.approval_decisions = SqlAlchemyApprovalDecisionRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)


class SqlAlchemyInvitationUnitOfWork:
    """organization invitations repo + audit writer — TEK session, TEK transaction.

    Cross-module compose (organization + audit) yalnız composition root'ta kurulur
    (ADR-009 §2b). Davet oluşturma/iptali + audit AYNI transaction'da commit edilir;
    RLS context transaction-local set_config ile taşınır.
    """

    invitations: InvitationRepository
    audit: AuditWriterPort

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyInvitationUnitOfWork:
        self._session = self._session_factory()
        self.invitations = SqlAlchemyInvitationRepository(self._session)
        self.audit = SqlAlchemyAuditWriter(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_actor_id', :value, true)"),
            {"value": str(actor_user_id)},
        )

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant_id)},
        )

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif degil — 'with uow:' blogu icinde kullanin.")
        return self._session


class SqlAlchemyInvitationAcceptUnitOfWork:
    """invitations + memberships + audit — TEK session, TEK transaction (davet kabulü).

    Kabul + üyelik oluşturma + audit AYNI transaction'da commit edilir (ADR-009 §2b
    compose). RLS context transaction-local set_config ile taşınır.
    """

    invitations: InvitationRepository
    memberships: MembershipWriteRepository
    idempotency: AcceptIdempotencyRepository
    audit: AuditWriterPort

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyInvitationAcceptUnitOfWork:
        self._session = self._session_factory()
        self.invitations = SqlAlchemyInvitationRepository(self._session)
        self.memberships = SqlAlchemyMembershipWriteRepository(self._session)
        self.idempotency = SqlAlchemyAcceptIdempotencyRepository(self._session)
        self.audit = SqlAlchemyAuditWriter(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_actor_id', :value, true)"),
            {"value": str(actor_user_id)},
        )

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant_id)},
        )

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif degil — 'with uow:' blogu icinde kullanin.")
        return self._session


class SqlAlchemyTaskInboxReadModel:
    """`TaskInboxQuery` — actor'a atanmış AKTİF task'ları PR verisiyle birleştiren read model.

    Cross-module JOIN (workflow_runtime_tasks + purchase_request_requests) yalnız
    composition root'ta (wiring dosyası) yapılır. RLS tenant-scoped; başka kullanıcının
    task'ı görünmez (assigned_user_id filtresi + policy).
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_pending_for_user(
        self, *, tenant_id: UUID, user_id: UUID, limit: int
    ) -> list[InboxItem]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    text(
                        "SELECT t.id AS task_id, t.instance_id, t.approver_role, t.status, "
                        "t.created_at, p.id AS pr_id, p.title, p.amount_minor, p.currency "
                        "FROM workflow_runtime_tasks t "
                        "JOIN purchase_request_requests p "
                        "  ON p.workflow_instance_id = t.instance_id "
                        "WHERE t.assigned_user_id = :user AND t.status = 'active' "
                        "ORDER BY t.created_at DESC, t.id DESC LIMIT :limit"
                    ),
                    {"user": str(user_id), "limit": limit},
                )
                .mappings()
                .all()
            )
        return [
            InboxItem(
                task_id=row["task_id"],
                purchase_request_id=row["pr_id"],
                purchase_request_title=str(row["title"]),
                amount_minor=int(row["amount_minor"]),
                currency=str(row["currency"]),
                required_role=str(row["approver_role"]),
                status=str(row["status"]),
                workflow_instance_id=row["instance_id"],
                created_at=row["created_at"],
                due_at=None,
            )
            for row in rows
        ]


class SqlAlchemyMemberListReadModel:
    """`MemberListQuery` — organization_memberships + identity_users (email) cross-module JOIN.

    Cross-module read yalnız composition root'ta. Tenant-scoped (RLS); YALNIZ email_snapshot
    döner (provider_subject / auth_provider DÖNMEZ). Removed üyeler durumlarıyla listede kalır.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_members(self, *, tenant_id: UUID, limit: int) -> list[MemberView]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    text(
                        "SELECT m.id AS membership_id, m.user_id, u.email_snapshot AS email, "
                        "m.role, m.status, m.version, m.created_at, m.updated_at "
                        "FROM organization_memberships m "
                        "LEFT JOIN identity_users u ON u.id = m.user_id "
                        "WHERE m.tenant_id = :t "
                        "ORDER BY m.created_at ASC, m.id ASC LIMIT :limit"
                    ),
                    {"t": str(tenant_id), "limit": limit},
                )
                .mappings()
                .all()
            )
        return [
            MemberView(
                membership_id=row["membership_id"],
                user_id=row["user_id"],
                email=row["email"],
                role=str(row["role"]),
                status=str(row["status"]),
                version=int(row["version"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


class SqlAlchemyApprovalResponsibilityReader:
    """`ApprovalResponsibilityQuery` — approval_role_assignments + workflow_runtime_tasks READ.

    Cross-module read yalnız composition root'ta; update UoW'nin session'ında (tenant context
    set edilmiş) çalışır. Aktif role assignment VEYA pending/active approval task = sorumluluk.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def has_active_responsibilities(self, *, tenant_id: UUID, user_id: UUID) -> bool:
        value = self._session.execute(
            text(
                "SELECT "
                "EXISTS(SELECT 1 FROM approval_role_assignments "
                "  WHERE tenant_id = :t AND assigned_user_id = :u AND status = 'active') "
                "OR EXISTS(SELECT 1 FROM workflow_runtime_tasks "
                "  WHERE tenant_id = :t AND assigned_user_id = :u "
                "  AND status IN ('pending','active'))"
            ),
            {"t": str(tenant_id), "u": str(user_id)},
        ).scalar_one()
        return bool(value)


class SqlAlchemyMemberUpdateUnitOfWork:
    """membership yönetimi + approval sorumluluk + audit — TEK session, TEK transaction.

    Cross-module compose (organization + approval/workflow read + audit) yalnız composition
    root'ta (ADR-009 §2b). RLS context transaction-local set_config ile taşınır.
    """

    memberships: MembershipManagementRepository
    approval_responsibility: ApprovalResponsibilityQuery
    audit: AuditWriterPort

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyMemberUpdateUnitOfWork:
        self._session = self._session_factory()
        self.memberships = SqlAlchemyMembershipManagementRepository(self._session)
        self.approval_responsibility = SqlAlchemyApprovalResponsibilityReader(self._session)
        self.audit = SqlAlchemyAuditWriter(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_actor_id', :value, true)"),
            {"value": str(actor_user_id)},
        )

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant_id)},
        )

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif degil — 'with uow:' blogu icinde kullanin.")
        return self._session


class SqlAlchemyApprovalRoleAssignmentListReadModel:
    """`ApprovalRoleAssignmentListQuery` — approval_role_assignments + identity_users JOIN.

    Cross-module read yalnız composition root'ta. Tenant-scoped (RLS); YALNIZ AKTİF atamalar,
    canonical role sırasında; YALNIZ email_snapshot döner (provider_subject/auth DÖNMEZ).
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_assignments(self, *, tenant_id: UUID) -> list[ApprovalRoleAssignmentView]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    text(
                        "SELECT a.id AS assignment_id, a.role_key, "
                        "a.assigned_user_id, u.email_snapshot AS email, a.status, "
                        "a.version, a.created_at, a.updated_at "
                        "FROM approval_role_assignments a "
                        "LEFT JOIN identity_users u ON u.id = a.assigned_user_id "
                        "WHERE a.tenant_id = :t AND a.status = 'active' "
                        # Canonical sıra: team_manager → finance → general_manager (sabit).
                        "ORDER BY CASE a.role_key WHEN 'team_manager' THEN 1 "
                        "WHEN 'finance' THEN 2 WHEN 'general_manager' THEN 3 ELSE 4 END, "
                        "a.role_key ASC"
                    ),
                    {"t": str(tenant_id)},
                )
                .mappings()
                .all()
            )
        return [
            ApprovalRoleAssignmentView(
                assignment_id=row["assignment_id"],
                role_key=str(row["role_key"]),
                assigned_user_id=row["assigned_user_id"],
                assigned_user_email=row["email"],
                status=str(row["status"]),
                version=int(row["version"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


class SqlAlchemyTargetMembershipReader:
    """`TargetMembershipReader` — organization_memberships + identity_users READ (any status).

    Cross-module read yalnız composition root'ta; update UoW'nin session'ında (tenant context
    set edilmiş) çalışır. Hedefin ANY-status üyeliğini döndürür → 404 (üye değil) ile 409
    (aktif değil) ayrımını mümkün kılar. Yalnız email_snapshot döner.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, *, tenant_id: UUID, user_id: UUID) -> TargetMembershipInfo | None:
        row = (
            self._session.execute(
                text(
                    "SELECT m.status, u.email_snapshot AS email "
                    "FROM organization_memberships m "
                    "LEFT JOIN identity_users u ON u.id = m.user_id "
                    "WHERE m.tenant_id = :t AND m.user_id = :u"
                ),
                {"t": str(tenant_id), "u": str(user_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return TargetMembershipInfo(status=str(row["status"]), email=row["email"])


class SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork:
    """rol atama yönetimi + hedef üyelik + audit — TEK session, TEK transaction.

    Cross-module compose (approval + organization read + audit) yalnız composition root'ta
    (ADR-009 §2b). RLS context transaction-local set_config ile taşınır.
    """

    assignments: ApprovalRoleAssignmentManagementRepository
    target_memberships: TargetMembershipReader
    audit: AuditWriterPort

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork:
        self._session = self._session_factory()
        self.assignments = SqlAlchemyApprovalRoleAssignmentManagementRepository(self._session)
        self.target_memberships = SqlAlchemyTargetMembershipReader(self._session)
        self.audit = SqlAlchemyAuditWriter(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_actor_id', :value, true)"),
            {"value": str(actor_user_id)},
        )

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant_id)},
        )

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif degil — 'with uow:' blogu icinde kullanin.")
        return self._session
