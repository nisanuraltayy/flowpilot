"""CreateOrganization use-case handler'ı.

Business transaction BURADA orkestre edilir (API veya repository içine gömülmez):

1. Actor kullanıcının var olduğu doğrulanır (cross-module `UserDirectory`).
2. Organization oluşturulur; RLS insert policy için actor context ayarlanır.
3. Owner membership oluşturulur; RLS için tenant context ayarlanır.
4. İkisi AYNI transaction'da persist edilir.
5. Commit başarılıysa sonuç döner; herhangi bir hata rollback ile sonuçlanır.
"""

from __future__ import annotations

from flowpilot.modules.identity.application.contracts import UserDirectory
from flowpilot.modules.organization.application.commands import (
    CreateOrganizationCommand,
    CreateOrganizationResult,
)
from flowpilot.modules.organization.application.errors import ActorNotFoundError
from flowpilot.modules.organization.application.ports import UnitOfWork
from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.domain.organization import Organization
from flowpilot.modules.organization.domain.organization_name import OrganizationName
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort


class CreateOrganizationHandler:
    """Organization oluşturma + owner membership atomik use-case'i."""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        user_directory: UserDirectory,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow = unit_of_work
        self._user_directory = user_directory
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: CreateOrganizationCommand) -> CreateOrganizationResult:
        # Ad doğrulaması transaction'dan önce (girdi hatası, DB'ye dokunmadan).
        name = OrganizationName(command.organization_name)
        actor_id = UserId(command.actor_user_id)

        with self._uow as uow:
            if not self._user_directory.exists(actor_id):
                raise ActorNotFoundError(command.actor_user_id)

            now = self._clock.now()
            tenant_id = TenantId(self._ids.new_uuid())
            organization = Organization.create(
                id=tenant_id,
                name=name,
                created_by=actor_id,
                created_at=now,
            )
            # RLS: tenant, YALNIZ current actor adına oluşturulabilir.
            uow.set_actor_context(command.actor_user_id)
            uow.organizations.add_tenant(organization)

            membership_id = MembershipId(self._ids.new_uuid())
            membership = Membership.create_owner(
                id=membership_id,
                tenant_id=tenant_id,
                user_id=actor_id,
                created_at=now,
            )
            # RLS: membership, YALNIZ current tenant scope'una eklenebilir.
            uow.set_tenant_context(tenant_id.value)
            uow.organizations.add_membership(membership)

            uow.commit()

        return CreateOrganizationResult(
            tenant_id=tenant_id.value,
            owner_membership_id=membership_id.value,
        )
