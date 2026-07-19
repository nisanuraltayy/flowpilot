"""Purchase Request domain: Money, title/description, state transition (unit)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.purchase_request.domain.errors import (
    InvalidDescriptionError,
    InvalidMoneyError,
    InvalidPurchaseRequestTransitionError,
    InvalidTitleError,
)
from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
from flowpilot.modules.purchase_request.domain.money import Money
from flowpilot.modules.purchase_request.domain.purchase_request import (
    PurchaseRequest,
    PurchaseRequestStatus,
)
from flowpilot.modules.purchase_request.domain.value_objects import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    PurchaseRequestDescription,
    PurchaseRequestTitle,
)
from flowpilot.shared.identifiers import TenantId, UserId

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


class TestMoney:
    def test_valid(self) -> None:
        money = Money(amount_minor=1_000_000, currency="TRY")
        assert money.amount_minor == 1_000_000

    def test_zero_rejected(self) -> None:
        with pytest.raises(InvalidMoneyError, match="0'dan büyük"):
            Money(amount_minor=0, currency="TRY")

    def test_negative_rejected(self) -> None:
        with pytest.raises(InvalidMoneyError, match="0'dan büyük"):
            Money(amount_minor=-5, currency="TRY")

    def test_float_rejected(self) -> None:
        with pytest.raises(InvalidMoneyError, match="tam sayı"):
            Money(amount_minor=100.5, currency="TRY")  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        with pytest.raises(InvalidMoneyError, match="tam sayı"):
            Money(amount_minor=True, currency="TRY")  # type: ignore[arg-type]

    @pytest.mark.parametrize("currency", ["USD", "EUR", "try", "GBP", ""])
    def test_non_try_currency_rejected(self, currency: str) -> None:
        with pytest.raises(InvalidMoneyError, match="para birimi"):
            Money(amount_minor=1000, currency=currency)


class TestTitle:
    def test_valid_trims(self) -> None:
        assert PurchaseRequestTitle("  Dizüstü  ").value == "Dizüstü"

    def test_blank_rejected(self) -> None:
        with pytest.raises(InvalidTitleError):
            PurchaseRequestTitle("   ")

    def test_empty_rejected(self) -> None:
        with pytest.raises(InvalidTitleError):
            PurchaseRequestTitle("")

    def test_max_length_ok(self) -> None:
        assert len(PurchaseRequestTitle("a" * TITLE_MAX_LENGTH).value) == TITLE_MAX_LENGTH

    def test_over_max_rejected(self) -> None:
        with pytest.raises(InvalidTitleError, match="en çok"):
            PurchaseRequestTitle("a" * (TITLE_MAX_LENGTH + 1))


class TestDescription:
    def test_none_is_none(self) -> None:
        assert PurchaseRequestDescription(None).value is None

    def test_blank_becomes_none(self) -> None:
        assert PurchaseRequestDescription("   ").value is None

    def test_trimmed(self) -> None:
        assert PurchaseRequestDescription("  x  ").value == "x"

    def test_over_max_rejected(self) -> None:
        with pytest.raises(InvalidDescriptionError, match="en çok"):
            PurchaseRequestDescription("a" * (DESCRIPTION_MAX_LENGTH + 1))


class TestPurchaseRequestAggregate:
    def _create(self) -> PurchaseRequest:
        request, _event = PurchaseRequest.create(
            id=PurchaseRequestId(uuid4()),
            tenant_id=TenantId(uuid4()),
            requested_by=UserId(uuid4()),
            title=PurchaseRequestTitle("Talep"),
            description=PurchaseRequestDescription(None),
            money=Money(amount_minor=500_000, currency="TRY"),
            created_at=NOW,
        )
        return request

    def test_create_is_draft_without_instance(self) -> None:
        request = self._create()
        assert request.status is PurchaseRequestStatus.DRAFT
        assert request.workflow_instance_id is None
        assert request.version == 1

    def test_create_emits_event(self) -> None:
        _request, event = PurchaseRequest.create(
            id=PurchaseRequestId(uuid4()),
            tenant_id=TenantId(uuid4()),
            requested_by=UserId(uuid4()),
            title=PurchaseRequestTitle("Talep"),
            description=PurchaseRequestDescription("gerekçe"),
            money=Money(amount_minor=500_000, currency="TRY"),
            created_at=NOW,
        )
        assert event.amount_minor == 500_000
        assert event.currency == "TRY"

    def test_attach_workflow_moves_to_in_approval(self) -> None:
        request = self._create()
        instance_id = uuid4()
        linked = request.attach_workflow(workflow_instance_id=instance_id, now=NOW)
        assert linked.status is PurchaseRequestStatus.IN_APPROVAL
        assert linked.workflow_instance_id == instance_id
        assert linked.version == 2
        # Orijinal immutable — değişmedi.
        assert request.status is PurchaseRequestStatus.DRAFT

    def test_attach_workflow_only_from_draft(self) -> None:
        request = self._create().attach_workflow(workflow_instance_id=uuid4(), now=NOW)
        with pytest.raises(InvalidPurchaseRequestTransitionError):
            request.attach_workflow(workflow_instance_id=uuid4(), now=NOW)
