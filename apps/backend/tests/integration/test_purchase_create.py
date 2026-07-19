"""CreatePurchaseRequest — gerçek DB: threshold, atomicity, authz, RLS, provisioning."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from flowpilot.modules.purchase_request.application.errors import MembershipNotActiveError
from flowpilot.modules.purchase_request.domain.errors import InvalidMoneyError
from tests.integration.purchase_support import (
    AMOUNT_10K,
    AMOUNT_50K,
    AMOUNT_OVER_50K,
    AMOUNT_UNDER_10K,
    build_create_handler,
    scoped_count,
    seed_tenant_with_member,
)


def _cmd(tenant: UUID, actor: UUID, amount: int) -> CreatePurchaseRequestCommand:
    return CreatePurchaseRequestCommand(
        actor_user_id=actor,
        tenant_id=tenant,
        title="Dizüstü bilgisayar",
        description="ekip için",
        amount_minor=amount,
        currency="TRY",
    )


def _chain(app_sessionmaker: sessionmaker[Session], tenant: UUID, instance_id: UUID) -> list[str]:
    with app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant)})
        rows = s.execute(
            text(
                "SELECT approver_role FROM workflow_runtime_tasks "
                "WHERE instance_id = :i ORDER BY step_index"
            ),
            {"i": str(instance_id)},
        ).all()
    return [str(r[0]) for r in rows]


@pytest.mark.parametrize(
    ("amount", "expected_chain"),
    [
        (AMOUNT_UNDER_10K, ["team_manager"]),
        (AMOUNT_10K, ["team_manager", "finance"]),
        (AMOUNT_50K, ["team_manager", "finance"]),
        (AMOUNT_OVER_50K, ["team_manager", "finance", "general_manager"]),
    ],
)
def test_threshold_boundaries_select_correct_chain(
    app_sessionmaker: sessionmaker[Session], amount: int, expected_chain: list[str]
) -> None:
    tenant, actor = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    result = handler.handle(_cmd(tenant, actor, amount))

    assert result.status == "in_approval"
    assert result.current_approval_role == expected_chain[0]
    assert _chain(app_sessionmaker, tenant, result.workflow_instance_id) == expected_chain


def test_create_writes_pr_instance_task_event_outbox_atomically(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, actor = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    result = handler.handle(_cmd(tenant, actor, AMOUNT_10K))

    pr_id = str(result.purchase_request_id)
    inst = str(result.workflow_instance_id)
    assert scoped_count(app_sessionmaker, tenant, "purchase_request_requests", id=pr_id) == 1
    assert scoped_count(app_sessionmaker, tenant, "workflow_runtime_instances", id=inst) == 1
    assert scoped_count(app_sessionmaker, tenant, "workflow_runtime_tasks", instance_id=inst) == 2
    assert (
        scoped_count(
            app_sessionmaker,
            tenant,
            "workflow_runtime_outbox",
            event_type="instance.form_submitted.v1",
        )
        == 1
    )
    # PR workflow_instance_id'ye bağlı ve in_approval.
    assert (
        scoped_count(
            app_sessionmaker,
            tenant,
            "purchase_request_requests",
            id=pr_id,
            status="in_approval",
            workflow_instance_id=inst,
        )
        == 1
    )


def test_inactive_membership_cannot_create(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, actor = seed_tenant_with_member(app_sessionmaker, status="suspended")
    handler = build_create_handler(app_sessionmaker)
    with pytest.raises(MembershipNotActiveError):
        handler.handle(_cmd(tenant, actor, AMOUNT_10K))
    assert scoped_count(app_sessionmaker, tenant, "purchase_request_requests") == 0


def test_non_member_of_other_tenant_cannot_create(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a, _actor_a = seed_tenant_with_member(app_sessionmaker)
    _tenant_b, actor_b = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    # actor_b, tenant_a'nın üyesi değil → kontrollü red, yarım kayıt yok.
    with pytest.raises(MembershipNotActiveError):
        handler.handle(_cmd(tenant_a, actor_b, AMOUNT_10K))
    assert scoped_count(app_sessionmaker, tenant_a, "purchase_request_requests") == 0


def test_invalid_amount_rejected(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, actor = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    with pytest.raises(InvalidMoneyError):
        handler.handle(_cmd(tenant, actor, 0))
    assert scoped_count(app_sessionmaker, tenant, "purchase_request_requests") == 0


def test_default_workflow_provisioned_once(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, actor = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    handler.handle(_cmd(tenant, actor, AMOUNT_10K))
    handler.handle(_cmd(tenant, actor, AMOUNT_50K))
    # İki talep, aynı tek published definition + version (idempotent provisioning).
    assert scoped_count(app_sessionmaker, tenant, "workflow_runtime_definitions") == 1
    assert scoped_count(app_sessionmaker, tenant, "workflow_runtime_definition_versions") == 1
    assert scoped_count(app_sessionmaker, tenant, "purchase_request_requests") == 2


def test_cross_tenant_pr_not_visible(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, actor_a = seed_tenant_with_member(app_sessionmaker)
    tenant_b, _actor_b = seed_tenant_with_member(app_sessionmaker)
    handler = build_create_handler(app_sessionmaker)
    result = handler.handle(_cmd(tenant_a, actor_a, AMOUNT_10K))

    # Tenant B context'inde A'nın talebi görünmez.
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_b,
            "purchase_request_requests",
            id=str(result.purchase_request_id),
        )
        == 0
    )
    # Context yoksa da görünmez.
    with app_sessionmaker() as s:
        count = s.execute(text("SELECT count(*) FROM purchase_request_requests")).scalar_one()
    assert count == 0


def test_atomic_rollback_when_runtime_fails(app_sessionmaker: sessionmaker[Session]) -> None:
    """Compose transaction'da workflow start başarısızsa PR kaydı da rollback olur."""
    tenant, actor = seed_tenant_with_member(app_sessionmaker)

    # Provisioning'i bozarak (geçersiz version_id) start_instance_tx'i patlatan bir
    # senaryo yerine, burada composed uow'u kullanıp fault enjekte ediyoruz: geçersiz
    # bir definition_version_id ile handler'ın runtime çağrısı NotFound üretir.
    from uuid import uuid4 as _uuid

    from flowpilot.api.wiring import SqlAlchemyPurchaseRequestUnitOfWork
    from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
    from flowpilot.modules.purchase_request.domain.money import Money
    from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
    from flowpilot.modules.purchase_request.domain.value_objects import (
        PurchaseRequestDescription,
        PurchaseRequestTitle,
    )
    from flowpilot.modules.workflow_runtime.application.dto import StartInstanceCommand
    from flowpilot.modules.workflow_runtime.domain.errors import DefinitionVersionNotFoundError
    from flowpilot.shared.clock import SystemClock
    from flowpilot.shared.identifiers import TenantId, UserId
    from tests.integration.purchase_support import build_runtime

    runtime = build_runtime(app_sessionmaker)
    now = SystemClock().now()
    request, _ = PurchaseRequest.create(
        id=PurchaseRequestId(_uuid()),
        tenant_id=TenantId(tenant),
        requested_by=UserId(actor),
        title=PurchaseRequestTitle("x"),
        description=PurchaseRequestDescription(None),
        money=Money(amount_minor=AMOUNT_10K, currency="TRY"),
        created_at=now,
    )
    with (
        pytest.raises(DefinitionVersionNotFoundError),
        SqlAlchemyPurchaseRequestUnitOfWork(app_sessionmaker) as uow,
    ):
        uow.set_actor_context(actor)
        uow.set_tenant_context(tenant)
        uow.purchase_requests.add(request)  # PR insert edildi (flush)
        runtime.start_instance_tx(
            uow,
            StartInstanceCommand(
                tenant_id=tenant,
                actor_user_id=actor,
                definition_version_id=_uuid(),  # var olmayan version → NotFound
                request_id="r",
            ),
        )
        uow.commit()
    # Exception → __exit__ rollback → PR kaydı KALMAZ.
    assert scoped_count(app_sessionmaker, tenant, "purchase_request_requests") == 0
