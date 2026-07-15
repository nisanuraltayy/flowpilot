"""Identity application-katmanı error'ları."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class DuplicateProviderIdentityError(DomainError):
    """Aynı (auth_provider, provider_subject) için ikinci insert denemesi.

    Infrastructure, DB unique constraint ihlalini bu hataya çevirir; handler
    yarışı kaybetmişse mevcut kullanıcıyı yeniden okuyarak çözer.
    """

    def __init__(self) -> None:
        super().__init__("Bu harici kimlik zaten bir kullaniciya bagli.")
