"""Approval/audit şema güvenliği — GERÇEK PostgreSQL.

Kapsam (migration 0005): append-only (UPDATE/DELETE reddi — grant + trigger),
RLS cross-tenant izolasyon, tenant+role başına TEK aktif assignee (partial unique).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


def _set_tenant(s: Session, tenant: str) -> None:
    s.execute(text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": tenant})


def _insert_assignment(s: Session, tenant: str, role: str, user: str) -> None:
    s.execute(
        text(
            "INSERT INTO approval_role_assignments "
            "(id, tenant_id, role_key, assigned_user_id, status, created_at, updated_at) "
            "VALUES (:id, :t, :r, :u, 'active', now(), now())"
        ),
        {"id": str(uuid4()), "t": tenant, "r": role, "u": user},
    )


def _insert_audit(s: Session, tenant: str, pr_id: str) -> str:
    audit_id = str(uuid4())
    s.execute(
        text(
            "INSERT INTO audit_entries "
            "(id, tenant_id, aggregate_type, aggregate_id, event_type, occurred_at) "
            "VALUES (:id, :t, 'purchase_request', :pr, 'purchase_request.created', now())"
        ),
        {"id": audit_id, "t": tenant, "pr": pr_id},
    )
    return audit_id


def test_one_active_assignee_per_role_partial_unique(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant = str(uuid4())
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        _insert_assignment(s, tenant, "finance", str(uuid4()))
    with pytest.raises(IntegrityError), app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        _insert_assignment(s, tenant, "finance", str(uuid4()))  # ikinci aktif → çakışma


def test_audit_entries_reject_update_and_delete_for_app_role(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant = str(uuid4())
    pr_id = str(uuid4())
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        _insert_audit(s, tenant, pr_id)
    # App rolüne UPDATE/DELETE grant'i YOK (append-only) → reddedilir.
    with pytest.raises((ProgrammingError, DBAPIError)), app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        s.execute(
            text("UPDATE audit_entries SET event_type = 'x' WHERE tenant_id = :t"), {"t": tenant}
        )
    with pytest.raises((ProgrammingError, DBAPIError)), app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        s.execute(text("DELETE FROM audit_entries WHERE tenant_id = :t"), {"t": tenant})


def test_audit_append_only_trigger_blocks_even_privileged_update(
    app_sessionmaker: sessionmaker[Session],
    migrator_sessionmaker: sessionmaker[Session],
) -> None:
    tenant = str(uuid4())
    pr_id = str(uuid4())
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        _insert_audit(s, tenant, pr_id)
    # Migrator (owner, UPDATE yetkili) bile BEFORE UPDATE trigger ile engellenir.
    # Tenant context set edilir ki FORCE RLS satırı görsün ve trigger ateşlensin.
    with pytest.raises(DBAPIError), migrator_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant)
        s.execute(
            text("UPDATE audit_entries SET event_type = 'x' WHERE tenant_id = :t"), {"t": tenant}
        )


def test_cross_tenant_assignment_and_audit_not_visible(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    pr_id = str(uuid4())
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_a)
        _insert_assignment(s, tenant_a, "team_manager", str(uuid4()))
        _insert_audit(s, tenant_a, pr_id)

    # Tenant B context'inde A'nın kayıtları görünmez (RLS).
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_b)
        assignments = s.execute(text("SELECT count(*) FROM approval_role_assignments")).scalar_one()
        audits = s.execute(text("SELECT count(*) FROM audit_entries")).scalar_one()
    assert assignments == 0
    assert audits == 0

    # Context yoksa da (default deny) görünmez.
    with app_sessionmaker() as s:
        no_ctx = s.execute(text("SELECT count(*) FROM audit_entries")).scalar_one()
    assert no_ctx == 0
