"""Approval decision + inbox + PR list + audit timeline — GERÇEK PostgreSQL + fake auth.

Uçtan uca akış: giriş → talep → koşul → sıralı onay → PR durumu → timeline. Self-approval
YASAKTIR (FP-E06-009): talep sahibi (owner) kendi talebini onaylayamaz; bu nedenle onaycı
roller ayrı bir AKTİF üyeye (approver) atanır ve kararları o verir. Token/secret sızmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from tests.integration.approval_role_support import build_assign_approval_role_handler
from tests.integration.invitation_support import add_member, create_tenant_with_owner, identity_for
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKENS = {"owner": "tok-owner", "approver": "tok-approver", "stranger": "tok-stranger"}


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider({token: identity_for(name) for name, token in TOKENS.items()})
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def org(app_sessionmaker: sessionmaker[Session]) -> dict[str, object]:
    """owner (talep sahibi) + approver (üç approval rolüne atanmış ayrı aktif üye)."""
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="approver", role="member")
    assign = build_assign_approval_role_handler(app_sessionmaker)
    for role in ("team_manager", "finance", "general_manager"):
        assign.handle(
            AssignApprovalRoleCommand(
                tenant_id=tenant,
                actor_user_id=owner,
                role_key=role,
                target_user_id=approver,
                expected_version=None,
            )
        )
    return {"id": tenant, "owner": owner, "approver": approver}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_pr(client: TestClient, org: object, token: str, amount: int) -> dict[str, object]:
    resp = client.post(
        f"/v1/organizations/{org}/purchase-requests",
        json={"title": "Talep", "amount_minor": amount, "currency": "TRY"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _inbox(client: TestClient, org: object, token: str) -> list[dict[str, object]]:
    resp = client.get(f"/v1/organizations/{org}/tasks/inbox", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _decide(
    client: TestClient, org: object, token: str, task_id: str, decision: str, key: str
) -> object:
    return client.post(
        f"/v1/organizations/{org}/tasks/{task_id}/decision",
        json={"decision": decision, "comment": "uygundur"},
        headers={**_auth(token), "Idempotency-Key": key},
    )


def _org_id(org: dict[str, object]) -> UUID:
    return org["id"]  # type: ignore[return-value]


def test_two_step_chain_full_approval_and_timeline(
    client: TestClient, org: dict[str, object]
) -> None:
    oid = _org_id(org)
    pr = _create_pr(client, oid, TOKENS["owner"], 1_250_000)  # 12.500 TL → team_manager, finance
    pr_id = str(pr["purchase_request_id"])

    # 1) Inbox: team_manager adımı approver'a atanmış (talep sahibine DEĞİL).
    inbox = _inbox(client, oid, TOKENS["approver"])
    assert len(inbox) == 1 and inbox[0]["required_role"] == "team_manager"
    assert _inbox(client, oid, TOKENS["owner"]) == []  # requester görmez
    task1 = str(inbox[0]["task_id"])

    # 2) İlk onay → sonraki adım finance.
    r1 = _decide(client, oid, TOKENS["approver"], task1, "approve", "k1")
    assert r1.status_code == 200, r1.text
    assert r1.json()["next_approval_role"] == "finance"
    assert r1.json()["purchase_request_status"] == "in_approval"

    # 3) Inbox artık finance adımını gösterir; nihai onay → approved/completed.
    task2 = str(_inbox(client, oid, TOKENS["approver"])[0]["task_id"])
    r2 = _decide(client, oid, TOKENS["approver"], task2, "approve", "k2")
    assert r2.status_code == 200, r2.text
    assert r2.json()["purchase_request_status"] == "approved"
    assert r2.json()["workflow_status"] == "completed"
    assert _inbox(client, oid, TOKENS["approver"]) == []

    # 4) Timeline sırası korunur.
    tl = client.get(
        f"/v1/organizations/{oid}/purchase-requests/{pr_id}/timeline",
        headers=_auth(TOKENS["owner"]),
    )
    assert tl.status_code == 200, tl.text
    events = [item["event_type"] for item in tl.json()["items"]]
    assert events == [
        "purchase_request.created",
        "workflow.started",
        "approval.task_assigned",
        "approval.approved",
        "approval.task_assigned",
        "approval.approved",
        "workflow.completed",
    ]


def test_three_step_chain_over_50k(client: TestClient, org: dict[str, object]) -> None:
    oid = _org_id(org)
    pr = _create_pr(client, oid, TOKENS["owner"], 5_000_001)  # >50k → 3 adım
    roles_seen = []
    for i in range(3):
        inbox = _inbox(client, oid, TOKENS["approver"])
        assert len(inbox) == 1
        roles_seen.append(inbox[0]["required_role"])
        resp = _decide(
            client, oid, TOKENS["approver"], str(inbox[0]["task_id"]), "approve", f"k{i}"
        )
        assert resp.status_code == 200, resp.text

    assert roles_seen == ["team_manager", "finance", "general_manager"]
    detail = client.get(
        f"/v1/organizations/{oid}/purchase-requests/{pr['purchase_request_id']}",
        headers=_auth(TOKENS["owner"]),
    ).json()
    assert detail["status"] == "approved"


def test_reject_at_first_step_sets_pr_rejected(client: TestClient, org: dict[str, object]) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 1_250_000)
    inbox = _inbox(client, oid, TOKENS["approver"])
    resp = _decide(client, oid, TOKENS["approver"], str(inbox[0]["task_id"]), "reject", "kr")
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchase_request_status"] == "rejected"
    assert _inbox(client, oid, TOKENS["approver"]) == []


def test_idempotent_replay_same_key_returns_duplicate(
    client: TestClient, org: dict[str, object]
) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 999_999)  # tek adım (team_manager)
    task = str(_inbox(client, oid, TOKENS["approver"])[0]["task_id"])

    first = _decide(client, oid, TOKENS["approver"], task, "approve", "same-key")
    assert first.status_code == 200 and first.json()["purchase_request_status"] == "approved"
    replay = _decide(client, oid, TOKENS["approver"], task, "approve", "same-key")
    assert replay.status_code == 200 and replay.json()["duplicate"] is True


def test_decided_task_with_different_key_conflicts(
    client: TestClient, org: dict[str, object]
) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 999_999)
    task = str(_inbox(client, oid, TOKENS["approver"])[0]["task_id"])
    assert _decide(client, oid, TOKENS["approver"], task, "approve", "key-1").status_code == 200
    conflict = _decide(client, oid, TOKENS["approver"], task, "approve", "key-2")
    assert conflict.status_code == 409, conflict.text


def test_decision_requires_idempotency_key(client: TestClient, org: dict[str, object]) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 999_999)
    task = str(_inbox(client, oid, TOKENS["approver"])[0]["task_id"])
    resp = client.post(
        f"/v1/organizations/{oid}/tasks/{task}/decision",
        json={"decision": "approve"},
        headers=_auth(TOKENS["approver"]),  # Idempotency-Key YOK
    )
    assert resp.status_code == 422


def test_pr_list_returns_only_own_requests(client: TestClient, org: dict[str, object]) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 1_000_000)
    _create_pr(client, oid, TOKENS["owner"], 2_000_000)
    resp = client.get(f"/v1/organizations/{oid}/purchase-requests", headers=_auth(TOKENS["owner"]))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    assert {i["amount_minor"] for i in items} == {1_000_000, 2_000_000}


def test_non_member_cannot_access_inbox_or_decide(
    client: TestClient, org: dict[str, object]
) -> None:
    oid = _org_id(org)
    _create_pr(client, oid, TOKENS["owner"], 999_999)
    task = str(_inbox(client, oid, TOKENS["approver"])[0]["task_id"])
    # stranger, org'da üye değil → inbox ve karar 404 (varlık sızmaz).
    assert (
        client.get(
            f"/v1/organizations/{oid}/tasks/inbox", headers=_auth(TOKENS["stranger"])
        ).status_code
        == 404
    )
    assert _decide(client, oid, TOKENS["stranger"], task, "approve", "kx").status_code == 404
