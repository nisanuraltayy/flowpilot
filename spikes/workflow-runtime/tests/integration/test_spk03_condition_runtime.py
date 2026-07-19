"""SPK-03 (integration) — Condition node runtime içinde doğru branch'i seçer.

Unit tarafı (sınır değer tablosu, zararlı payload, determinizm):
tests/unit/test_conditions.py. Burada branch seçiminin GERÇEK PostgreSQL
üzerinde doğru onay zincirini yarattığı, gerekçenin timeline'a (node_executions)
ve audit'e yazıldığı kanıtlanır.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.errors import ConditionEvaluationError

from .conftest import T0
from .flow_helpers import publish_v1, scoped_count, start_and_submit


@pytest.mark.parametrize(
    ("amount_minor", "expected_roles"),
    [
        (999_999, ["team_manager"]),
        (1_000_000, ["team_manager", "finance"]),
        (5_000_000, ["team_manager", "finance"]),
        (5_000_001, ["team_manager", "finance", "general_manager"]),
    ],
)
def test_branch_creates_correct_chain(
    app_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
    amount_minor: int,
    expected_roles: list[str],
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, amount_minor, T0)
    assert flow.step_roles == expected_roles

    # Gerekçe timeline'da görünür ve açıklanabilir (PRD §36.1 açıklanabilirlik).
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        detail = s.execute(
            text(
                "SELECT detail FROM spike_node_executions "
                "WHERE instance_id = :i AND node_type = 'condition'"
            ),
            {"i": str(flow.instance_id)},
        ).scalar_one()
    assert "explanation" in detail
    assert str(amount_minor) in detail["explanation"] or "otherwise" in detail["explanation"]


def test_currency_mismatch_rolls_back_whole_submit(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    """Kontrollü hata: crash yok, sessiz false yok — ve KISMİ yazım yok."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    requester = uuid.uuid4()
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(requester))
        instance = rt.start_instance(
            s,
            tenant_id=tenant_a,
            workflow_version_id=v1.id,
            requester_id=requester,
            request_id="req",
            now=T0,
        )

    with pytest.raises(ConditionEvaluationError, match="para birimi"), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(requester))
        rt.submit_form(
            s,
            tenant_id=tenant_a,
            instance_id=instance.id,
            form_data={"amount_minor": 1_000_000, "currency": "USD"},
            actor_id=requester,
            request_id="req",
            expected_version=instance.version,
            now=T0,
        )

    # Rollback: approval step de node_execution'ın form/condition kaydı da yok.
    assert scoped_count(app_sf, tenant_a, "spike_approval_steps") == 0
    assert scoped_count(app_sf, tenant_a, "spike_node_executions", node_type="condition") == 0
