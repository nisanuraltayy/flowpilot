"""Money value object — minor unit (integer) + ISO-4217 currency (FF-09).

Para float olarak TUTULAMAZ. Tutar iki alan birlikte taşınır; currency olmadan
tutar geçersizdir. MVP'de yalnız TRY desteklenir (mvp-scope §6, [[ASM-0002]]).
Eşikler BURADA değildir; workflow definition'ın Condition node'undadır.
"""

from __future__ import annotations

from dataclasses import dataclass

from flowpilot.modules.purchase_request.domain.errors import InvalidMoneyError

SUPPORTED_CURRENCIES = frozenset({"TRY"})


@dataclass(frozen=True, slots=True)
class Money:
    """Minor unit (kuruş) + currency. 10.000 TL = 1_000_000 minor unit."""

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise InvalidMoneyError("tutar minor unit (tam sayı) olmalı; float YASAK")
        if self.amount_minor <= 0:
            raise InvalidMoneyError("tutar 0'dan büyük olmalı")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise InvalidMoneyError(
                f"desteklenmeyen para birimi: {self.currency!r} (MVP'de yalnız TRY)"
            )
