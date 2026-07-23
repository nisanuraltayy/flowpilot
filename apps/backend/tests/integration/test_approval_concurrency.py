"""Approval kararı eşzamanlılığı — GERÇEK PostgreSQL: ilk geçerli karar kazanır.

İki eşzamanlı karar (çift tıklama / iki cihaz) aynı task üzerinde: tam olarak BİR
state transition + BİR approval_decisions kaydı oluşur (unique task_id + version CAS).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.dto import (
    DecideApprovalTaskCommand,
    DecideApprovalTaskResult,
)
from flowpilot.modules.approval.application.errors import DuplicateDecisionConflictError
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from tests.integration.purchase_support import (
    AMOUNT_UNDER_10K,
    active_task_id,
    build_create_handler,
    build_decide_handler,
    scoped_count,
    seed_tenant_requester_approver,
)

pytestmark = pytest.mark.integration


def test_concurrent_decisions_single_winner(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, requester, approver = seed_tenant_requester_approver(app_sessionmaker)
    created = build_create_handler(app_sessionmaker).handle(
        CreatePurchaseRequestCommand(
            actor_user_id=requester,
            tenant_id=tenant,
            title="Talep",
            description=None,
            amount_minor=AMOUNT_UNDER_10K,  # tek adım (team_manager)
            currency="TRY",
        )
    )
    task = active_task_id(app_sessionmaker, tenant, created.workflow_instance_id)
    decider = build_decide_handler(app_sessionmaker)

    def attempt(_: int) -> object:
        try:
            return decider.handle(
                DecideApprovalTaskCommand(
                    tenant_id=tenant,
                    actor_user_id=approver,  # onaycı = talep sahibinden AYRI (self-approval yasak)
                    task_id=task,
                    decision="approve",
                    comment=None,
                    idempotency_key="double-click",  # aynı key → idempotent
                )
            )
        except DuplicateDecisionConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, DecideApprovalTaskResult) and not o.duplicate]
    assert len(winners) == 1, f"tam olarak bir kazanan bekleniyordu: {outcomes}"
    # Diğer sonuç: idempotent duplicate ya da kontrollü conflict.
    for other in outcomes:
        if other not in winners:
            assert isinstance(other, DecideApprovalTaskResult | DuplicateDecisionConflictError)

    # DB'de TEK karar kaydı + PR approved.
    assert scoped_count(app_sessionmaker, tenant, "approval_decisions", task_id=str(task)) == 1
    assert (
        scoped_count(
            app_sessionmaker,
            tenant,
            "purchase_request_requests",
            id=str(created.purchase_request_id),
            status="approved",
        )
        == 1
    )
