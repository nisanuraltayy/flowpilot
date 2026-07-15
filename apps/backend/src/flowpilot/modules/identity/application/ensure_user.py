"""EnsureAuthenticatedUser use-case'i.

Doğrulanmış harici kimliği internal FlowPilot kullanıcısına eşler; kullanıcı
yoksa oluşturur. İDEMPOTENTTİR ve concurrent isteklere dayanıklıdır:

- Yarış koruması application-level `find` kontrolüne DEĞİL, DB unique
  constraint'ine dayanır: uq(auth_provider, provider_subject).
- İki eşzamanlı istek aynı subject'i insert etmeye çalışırsa biri
  `DuplicateProviderIdentityError` alır, rollback edip kazananın kaydını okur.
- E-posta değişse bile aynı internal user döner (e-posta identity DEĞİLDİR).

NOT: Bu işlem, organization oluşturma transaction'ından BAĞIMSIZDIR.
Organization işlemi sonradan başarısız olursa internal identity kaydının
kalması KABUL EDİLİR ve zararsızdır — kayıt yalnız "bu harici kimlik bu
internal user'dır" eşlemesidir; bir sonraki istekte aynen yeniden kullanılır.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.application.errors import DuplicateProviderIdentityError
from flowpilot.modules.identity.application.ports import IdentityUnitOfWork
from flowpilot.modules.identity.domain.user import User
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import UserId
from flowpilot.shared.ids import IdGeneratorPort


class EnsureAuthenticatedUserHandler:
    """Doğrulanmış kimlik → internal UserId (idempotent)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: Callable[[], IdentityUnitOfWork],
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock
        self._ids = id_generator

    def handle(self, identity: AuthenticatedIdentity) -> UUID:
        with self._uow_factory() as uow:
            existing = uow.users.find_by_provider_identity(
                identity.provider, identity.provider_subject
            )
            if existing is not None:
                return existing.id.value

            user = User.from_external_identity(
                id=UserId(self._ids.new_uuid()),
                auth_provider=identity.provider,
                provider_subject=identity.provider_subject,
                email_snapshot=identity.email,
                created_at=self._clock.now(),
            )
            try:
                uow.users.add(user)
                uow.commit()
            except DuplicateProviderIdentityError:
                # Yarışı kaybettik: kazananın kaydını çöz.
                uow.rollback()
                winner = uow.users.find_by_provider_identity(
                    identity.provider, identity.provider_subject
                )
                if winner is None:  # pragma: no cover — teorik olarak imkânsız
                    raise
                return winner.id.value
            return user.id.value
