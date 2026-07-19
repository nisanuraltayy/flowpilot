"""Approval decision + inbox + PR list + audit timeline — GERÇEK PostgreSQL + fake auth.

Uçtan uca akış (owner tek kullanıcı; self-approval SERBEST — owner #7, ASM-0016):
giriş → talep → koşul → sıralı onay → PR durumu → timeline. Token/secret sızmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKEN_A = "appr-token-a"
TOKEN_B = "appr-token-b"


def _identity(subject: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email=f"{subject}@example.com",
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider(
        {TOKEN_A: _identity("appr-sub-a"), TOKEN_B: _identity("appr-sub-b")}
    )
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_org(client: TestClient, token: str, name: str = "Acme") -> str:
    resp = client.post("/v1/organizations", json={"name": name}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return str(resp.json()["organization_id"])


def _create_pr(client: TestClient, org: str, token: str, amount: int) -> dict[str, object]:
    resp = client.post(
        f"/v1/organizations/{org}/purchase-requests",
        json={"title": "Talep", "amount_minor": amount, "currency": "TRY"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _inbox(client: TestClient, org: str, token: str) -> list[dict[str, object]]:
    resp = client.get(f"/v1/organizations/{org}/tasks/inbox", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _decide(
    client: TestClient, org: str, token: str, task_id: str, decision: str, key: str
) -> object:
    return client.post(
        f"/v1/organizations/{org}/tasks/{task_id}/decision",
        json={"decision": decision, "comment": "uygundur"},
        headers={**_auth(token), "Idempotency-Key": key},
    )


def test_two_step_chain_full_approval_and_timeline(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    pr = _create_pr(client, org, TOKEN_A, 1_250_000)  # 12.500 TL → team_manager, finance
    pr_id = str(pr["purchase_request_id"])

    # 1) Inbox: team_manager adımı owner'a atanmış.
    inbox = _inbox(client, org, TOKEN_A)
    assert len(inbox) == 1
    assert inbox[0]["required_role"] == "team_manager"
    task1 = str(inbox[0]["task_id"])

    # 2) İlk onay → sonraki adım finance, PR hâlâ in_approval.
    r1 = _decide(client, org, TOKEN_A, task1, "approve", "k1")
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["next_approval_role"] == "finance"
    assert b1["purchase_request_status"] == "in_approval"

    # 3) Inbox artık finance adımını gösterir.
    inbox2 = _inbox(client, org, TOKEN_A)
    assert len(inbox2) == 1
    assert inbox2[0]["required_role"] == "finance"
    task2 = str(inbox2[0]["task_id"])

    # 4) Nihai onay → PR approved, workflow completed.
    r2 = _decide(client, org, TOKEN_A, task2, "approve", "k2")
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["purchase_request_status"] == "approved"
    assert b2["workflow_status"] == "completed"

    # 5) Inbox boş.
    assert _inbox(client, org, TOKEN_A) == []

    # 6) Timeline sırası: create → started → task_assigned → approved → task_assigned
    #    → approved → completed.
    tl = client.get(
        f"/v1/organizations/{org}/purchase-requests/{pr_id}/timeline", headers=_auth(TOKEN_A)
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


def test_three_step_chain_over_50k(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    pr = _create_pr(client, org, TOKEN_A, 5_000_001)  # >50k → 3 adım
    roles_seen = []
    for i in range(3):
        inbox = _inbox(client, org, TOKEN_A)
        assert len(inbox) == 1
        roles_seen.append(inbox[0]["required_role"])
        resp = _decide(client, org, TOKEN_A, str(inbox[0]["task_id"]), "approve", f"k{i}")
        assert resp.status_code == 200, resp.text

    assert roles_seen == ["team_manager", "finance", "general_manager"]
    detail = client.get(
        f"/v1/organizations/{org}/purchase-requests/{pr['purchase_request_id']}",
        headers=_auth(TOKEN_A),
    ).json()
    assert detail["status"] == "approved"


def test_reject_at_first_step_sets_pr_rejected(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    _create_pr(client, org, TOKEN_A, 1_250_000)
    inbox = _inbox(client, org, TOKEN_A)
    resp = _decide(client, org, TOKEN_A, str(inbox[0]["task_id"]), "reject", "kr")
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchase_request_status"] == "rejected"
    assert _inbox(client, org, TOKEN_A) == []


def test_idempotent_replay_same_key_returns_duplicate(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    _create_pr(client, org, TOKEN_A, 999_999)  # tek adım (team_manager)
    task = str(_inbox(client, org, TOKEN_A)[0]["task_id"])

    first = _decide(client, org, TOKEN_A, task, "approve", "same-key")
    assert first.status_code == 200, first.text
    assert first.json()["purchase_request_status"] == "approved"

    replay = _decide(client, org, TOKEN_A, task, "approve", "same-key")
    assert replay.status_code == 200, replay.text
    assert replay.json()["duplicate"] is True


def test_decided_task_with_different_key_conflicts(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    _create_pr(client, org, TOKEN_A, 999_999)
    task = str(_inbox(client, org, TOKEN_A)[0]["task_id"])
    assert _decide(client, org, TOKEN_A, task, "approve", "key-1").status_code == 200

    conflict = _decide(client, org, TOKEN_A, task, "approve", "key-2")
    assert conflict.status_code == 409, conflict.text


def test_decision_requires_idempotency_key(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    _create_pr(client, org, TOKEN_A, 999_999)
    task = str(_inbox(client, org, TOKEN_A)[0]["task_id"])
    resp = client.post(
        f"/v1/organizations/{org}/tasks/{task}/decision",
        json={"decision": "approve"},
        headers=_auth(TOKEN_A),  # Idempotency-Key YOK
    )
    assert resp.status_code == 422


def test_pr_list_returns_only_own_requests(client: TestClient) -> None:
    org = _create_org(client, TOKEN_A)
    _create_pr(client, org, TOKEN_A, 1_000_000)
    _create_pr(client, org, TOKEN_A, 2_000_000)
    resp = client.get(f"/v1/organizations/{org}/purchase-requests", headers=_auth(TOKEN_A))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    # En yeni önce (created_at desc).
    assert {i["amount_minor"] for i in items} == {1_000_000, 2_000_000}


def test_non_member_cannot_access_inbox_or_decide(client: TestClient) -> None:
    org_a = _create_org(client, TOKEN_A, name="A")
    _create_org(client, TOKEN_B, name="B")
    _create_pr(client, org_a, TOKEN_A, 999_999)
    task = str(_inbox(client, org_a, TOKEN_A)[0]["task_id"])

    # Token B, A'nın org'unda üye değil → inbox ve karar 404 (varlık sızmaz).
    assert (
        client.get(f"/v1/organizations/{org_a}/tasks/inbox", headers=_auth(TOKEN_B)).status_code
        == 404
    )
    assert _decide(client, org_a, TOKEN_B, task, "approve", "kx").status_code == 404
