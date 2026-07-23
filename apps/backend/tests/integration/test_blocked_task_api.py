"""Blocked approval task API — GERÇEK PostgreSQL (Testcontainers) + fake auth.

GET blocked list + POST resolve-assignment; authorization, güvenli çözümleme, resource hiding.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from tests.integration.approval_role_support import (
    active_assignment,
    build_assign_approval_role_handler,
)
from tests.integration.blocked_task_support import task_row
from tests.integration.invitation_support import add_member, create_tenant_with_owner, identity_for
from tests.integration.purchase_support import AMOUNT_UNDER_10K, build_create_handler
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKENS = {
    "owner": "tok-owner",
    "member": "tok-member",
    "approver": "tok-approver",
    "stranger": "tok-stranger",
}


def _auth(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[who]}"}


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider({token: identity_for(name) for name, token in TOKENS.items()})
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


def _assign(
    app_sm: sessionmaker[Session], tenant: UUID, owner: UUID, role: str, target: UUID
) -> None:
    current = active_assignment(app_sm, tenant_id=tenant, role_key=role)
    build_assign_approval_role_handler(app_sm).handle(
        AssignApprovalRoleCommand(
            tenant_id=tenant,
            actor_user_id=owner,
            role_key=role,
            target_user_id=target,
            expected_version=int(current["version"]) if current else None,
        )
    )


@pytest.fixture
def blocked(app_sessionmaker: sessionmaker[Session]) -> dict[str, object]:
    """Bir blocked team_manager task'ı olan org: requester==team_manager → step0 blocked."""
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    add_member(app_sessionmaker, tenant_id=tenant, subject="member", role="member")
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="approver", role="member")
    _assign(app_sessionmaker, tenant, owner, "team_manager", owner)  # owner = requester = tm
    created = build_create_handler(app_sessionmaker).handle(
        CreatePurchaseRequestCommand(
            actor_user_id=owner,
            tenant_id=tenant,
            title="Talep",
            description=None,
            amount_minor=AMOUNT_UNDER_10K,
            currency="TRY",
        )
    )
    row = task_row(
        app_sessionmaker,
        tenant_id=tenant,
        instance_id=created.workflow_instance_id,
        role="team_manager",
    )
    return {"id": tenant, "owner": owner, "approver": approver, "task_id": UUID(str(row["id"]))}


def _blocked_url(tenant: object) -> str:
    return f"/v1/organizations/{tenant}/approval-tasks/blocked"


def _resolve_url(tenant: object, task_id: object) -> str:
    return f"/v1/organizations/{tenant}/approval-tasks/{task_id}/resolve-assignment"


# =============================== GET blocked ================================


def test_owner_lists_blocked_no_sensitive_fields(
    client: TestClient, blocked: dict[str, object]
) -> None:
    resp = client.get(_blocked_url(blocked["id"]), headers=_auth("owner"))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1 and items[0]["approver_role"] == "team_manager"
    assert items[0]["status"] == "blocked"
    assert items[0]["blocked_reason"] == "self_approval_no_eligible_assignee"
    assert set(items[0]) == {
        "task_id",
        "purchase_request_id",
        "approver_role",
        "status",
        "blocked_reason",
        "requester_user_id",
        "version",
        "created_at",
        "updated_at",
    }
    assert "provider_subject" not in resp.text and "supabase" not in resp.text


def test_member_list_forbidden(client: TestClient, blocked: dict[str, object]) -> None:
    assert client.get(_blocked_url(blocked["id"]), headers=_auth("member")).status_code == 403


def test_stranger_list_not_found(client: TestClient, blocked: dict[str, object]) -> None:
    assert client.get(_blocked_url(blocked["id"]), headers=_auth("stranger")).status_code == 404


def test_list_requires_auth(client: TestClient, blocked: dict[str, object]) -> None:
    assert client.get(_blocked_url(blocked["id"])).status_code == 401


# =============================== POST resolve ==============================


def test_resolve_requires_auth(client: TestClient, blocked: dict[str, object]) -> None:
    resp = client.post(_resolve_url(blocked["id"], blocked["task_id"]))
    assert resp.status_code == 401


def test_member_resolve_forbidden(client: TestClient, blocked: dict[str, object]) -> None:
    resp = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("member"))
    assert resp.status_code == 403


def test_stranger_resolve_not_found(client: TestClient, blocked: dict[str, object]) -> None:
    resp = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("stranger"))
    assert resp.status_code == 404


def test_resolve_task_not_found(client: TestClient, blocked: dict[str, object]) -> None:
    resp = client.post(_resolve_url(blocked["id"], uuid4()), headers=_auth("owner"))
    assert resp.status_code == 404


def test_resolve_conflict_when_no_eligible_assignee(
    client: TestClient, blocked: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    # team_manager hâlâ requester(owner)'a atalı → aday requester → 409.
    resp = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("owner"))
    assert resp.status_code == 409


def test_resolve_happy_assigns_eligible_and_activates(
    client: TestClient, blocked: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    # team_manager'ı uygun approver'a ata → resolve → task active + approver assigned.
    _assign(app_sessionmaker, blocked["id"], blocked["owner"], "team_manager", blocked["approver"])  # type: ignore[arg-type]
    resp = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("owner"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["assigned_user_id"] == str(blocked["approver"])
    assert body["approver_role"] == "team_manager"
    # blocked-list artık boş.
    after = client.get(_blocked_url(blocked["id"]), headers=_auth("owner")).json()["items"]
    assert after == []


def test_resolve_conflict_when_not_blocked(
    client: TestClient, blocked: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    # Önce resolve et (active olur), sonra tekrar resolve → 409 (blocked değil).
    _assign(app_sessionmaker, blocked["id"], blocked["owner"], "team_manager", blocked["approver"])  # type: ignore[arg-type]
    first = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("owner"))
    assert first.status_code == 200
    second = client.post(_resolve_url(blocked["id"], blocked["task_id"]), headers=_auth("owner"))
    assert second.status_code == 409


def test_cross_tenant_resolve_not_found(
    client: TestClient, blocked: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    # owner-b (TOKENS['owner'] değil) — owner A, B'de üye değil → 404. B'nin task_id'si yok;
    # owner A'nın task'ını B tenant path'inde çözmeye çalış → 404 (RLS/tenant izolasyonu).
    resp = client.post(_resolve_url(tenant_b, blocked["task_id"]), headers=_auth("owner"))
    assert resp.status_code == 404
