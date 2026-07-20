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

from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider


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
