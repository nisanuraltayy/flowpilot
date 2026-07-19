"""Purchase Request application (use-case) hataları — kontrollü, güvenli.

Domain validation/concurrency hataları da BURADAN yeniden dışa verilir; presentation
(composition root router) YALNIZ bu application sınırından yakalar — purchase_request
domain'i doğrudan import ETMEZ (dependency-rules §2, composition root → domain yasak).
"""

from __future__ import annotations

from flowpilot.modules.purchase_request.domain.errors import (
    InvalidDescriptionError,
    InvalidMoneyError,
    InvalidTitleError,
    PurchaseRequestConcurrencyError,
)
from flowpilot.shared.errors import DomainError

__all__ = [
    "FirstApprovalTaskMissingError",
    "InvalidDescriptionError",
    "InvalidMoneyError",
    "InvalidTitleError",
    "MembershipNotActiveError",
    "PurchaseRequestConcurrencyError",
    "WorkflowConfigurationError",
]


class MembershipNotActiveError(DomainError):
    """Actor bu tenant'ta aktif üye değil — tenant varlığı SIZDIRILMAZ (güvenli 404)."""


class WorkflowConfigurationError(DomainError):
    """Varsayılan workflow provision edilemedi/çözülemedi (güvenli 409/503)."""


class FirstApprovalTaskMissingError(DomainError):
    """Beklenen ilk approval task oluşmadı — kontrollü hata, yarım kayıt bırakmaz."""
