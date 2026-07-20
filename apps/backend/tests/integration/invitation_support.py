"""Invitation integration testleri için ortak yardımcılar (pytest toplamaz).

Gerçek organization tablolarına RLS policy yollarını kullanarak tenant/üye yazar ve
identity_users satırlarını BİLİNEN provider_subject ile oluşturur — böylece FakeAuthProvider
token'ı ensure_user üzerinden aynı seeded user_id'ye eşler.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.wiring import (
    SqlAlchemyInvitationAcceptUnitOfWork,
    SqlAlchemyInvitationUnitOfWork,
)
from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.infrastructure.persistence.user_directory import (
    SqlAlchemyUserDirectory,
)
from flowpilot.modules.organization.application.invitation_accept import (
    AcceptInvitationHandler,
    PreviewInvitationHandler,
)
from flowpilot.modules.organization.application.invitation_handlers import (
    CreateInvitationHandler,
    RevokeInvitationHandler,
)
from flowpilot.modules.organization.infrastructure.accept_url_builder import (
    SettingsInvitationAcceptUrlBuilder,
)
from flowpilot.modules.organization.infrastructure.persistence.invitation_preview_query import (
    SqlAlchemyInvitationPreviewQuery,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_query import (
    SqlAlchemyMembershipQuery,
)
from flowpilot.modules.organization.infrastructure.token_generator import (
    SecretsInvitationTokenGenerator,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator


def build_accept_invitation_handler(
    app_sessionmaker: sessionmaker[Session],
) -> AcceptInvitationHandler:
    return AcceptInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationAcceptUnitOfWork(app_sessionmaker),
        email_reader=SqlAlchemyUserDirectory(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_preview_invitation_handler(
    app_sessionmaker: sessionmaker[Session],
) -> PreviewInvitationHandler:
    return PreviewInvitationHandler(
        preview_query=SqlAlchemyInvitationPreviewQuery(app_sessionmaker),
        clock=SystemClock(),
    )


def seed_identity(app_sessionmaker: sessionmaker[Session], *, email: str) -> UUID:
    """identity_users satırı ekler (üyelik YOK); email_snapshot = email. user_id döndürür."""
    user_id = uuid4()
    with app_sessionmaker() as s, s.begin():
        _insert_identity_with_email(s, user_id=user_id, email=email)
    return user_id


def membership_row(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, user_id: UUID
) -> dict[str, object] | None:
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = (
            s.execute(
                text(
                    "SELECT id, role, status FROM organization_memberships "
                    "WHERE tenant_id = :t AND user_id = :u"
                ),
                {"t": str(tenant_id), "u": str(user_id)},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def audit_event_count(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, event_type: str
) -> int:
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        value = s.execute(
            text("SELECT count(*) FROM audit_entries WHERE tenant_id = :t AND event_type = :e"),
            {"t": str(tenant_id), "e": event_type},
        ).scalar_one()
    return int(value)


def accept_idempotency_count(app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID) -> int:
    """Bir tenant scope'undaki davet kabul idempotency kaydı sayısı (tenant context ile)."""
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        value = s.execute(
            text(
                "SELECT count(*) FROM organization_invitation_accept_idempotency "
                "WHERE tenant_id = :t"
            ),
            {"t": str(tenant_id)},
        ).scalar_one()
    return int(value)


def build_create_invitation_handler(
    app_sessionmaker: sessionmaker[Session], *, frontend_base_url: str | None = None
) -> CreateInvitationHandler:
    """Gerçek adapter'larla CreateInvitationHandler (deps.py wiring'ini yansıtır)."""
    return CreateInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationUnitOfWork(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
        email_lookup=SqlAlchemyUserDirectory(app_sessionmaker),
        token_generator=SecretsInvitationTokenGenerator(),
        accept_url_builder=SettingsInvitationAcceptUrlBuilder(frontend_base_url),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_revoke_invitation_handler(
    app_sessionmaker: sessionmaker[Session],
) -> RevokeInvitationHandler:
    return RevokeInvitationHandler(
        unit_of_work_factory=lambda: SqlAlchemyInvitationUnitOfWork(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def force_past_expiry(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, invitation_id: UUID
) -> None:
    """Bir bekleyen davetin expires_at'ini geçmişe çeker (status='pending' kalır).

    TTL'in dolmasını simüle eder; RLS UPDATE policy'sinden geçer (tenant context set edilir).
    """
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "UPDATE organization_invitations SET expires_at = now() - interval '1 day' "
                "WHERE id = :i AND status = 'pending'"
            ),
            {"i": str(invitation_id)},
        )


def identity_for(subject: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email=f"{subject}@example.com",
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


def _insert_identity(session: Session, *, user_id: UUID, subject: str) -> None:
    session.execute(
        text(
            "INSERT INTO identity_users (id, email_snapshot, auth_provider, "
            "provider_subject, created_at) VALUES (:id, :email, 'supabase', :sub, now())"
        ),
        {"id": str(user_id), "email": f"{subject}@example.com", "sub": subject},
    )


def _insert_identity_with_email(session: Session, *, user_id: UUID, email: str) -> None:
    session.execute(
        text(
            "INSERT INTO identity_users (id, email_snapshot, auth_provider, "
            "provider_subject, created_at) VALUES (:id, :email, 'supabase', :sub, now())"
        ),
        {"id": str(user_id), "email": email, "sub": str(user_id)},
    )


def create_tenant_with_owner(
    app_sessionmaker: sessionmaker[Session], *, owner_subject: str
) -> tuple[UUID, UUID]:
    """identity(owner) + tenant + aktif owner membership yaratır; (tenant_id, owner_id)."""
    tenant_id = uuid4()
    owner_id = uuid4()
    with app_sessionmaker() as s, s.begin():
        _insert_identity(s, user_id=owner_id, subject=owner_subject)
    with app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(owner_id)})
        s.execute(
            text(
                "INSERT INTO organization_tenants (id, name, status, created_by_user_id, "
                "created_at) VALUES (:id, :name, 'active', :actor, now())"
            ),
            {"id": str(tenant_id), "name": "Test Org", "actor": str(owner_id)},
        )
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                "created_at) VALUES (:id, :tenant, :user, 'owner', 'active', now())"
            ),
            {"id": str(uuid4()), "tenant": str(tenant_id), "user": str(owner_id)},
        )
    return tenant_id, owner_id


def add_member(
    app_sessionmaker: sessionmaker[Session],
    *,
    tenant_id: UUID,
    subject: str,
    role: str,
    status: str = "active",
) -> UUID:
    """Var olan tenant'a identity + membership ekler; user_id döndürür."""
    user_id = uuid4()
    with app_sessionmaker() as s, s.begin():
        _insert_identity(s, user_id=user_id, subject=subject)
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                "created_at) VALUES (:id, :tenant, :user, :role, :status, now())"
            ),
            {
                "id": str(uuid4()),
                "tenant": str(tenant_id),
                "user": str(user_id),
                "role": role,
                "status": status,
            },
        )
    return user_id


def invitation_rows(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID
) -> list[dict[str, object]]:
    """Tenant scope'undaki davet satırlarını (token_hash dahil) okur — DB doğrulaması için."""
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        rows = (
            s.execute(
                text(
                    "SELECT id, invited_email, role, token_hash, status, expires_at, version "
                    "FROM organization_invitations WHERE tenant_id = :t"
                ),
                {"t": str(tenant_id)},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]
