import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { assignApprovalRoleAction } from "@/features/approval-roles/actions";
import { ApprovalRoleList } from "@/features/approval-roles/approval-role-list";
import { canManageApprovalRoles } from "@/features/approval-roles/permissions";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { listApprovalRoleAssignments, listOrganizationMembers } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Onay Rolleri" };

const APPROVAL_ROLES_PATH = "/settings/team/approval-roles";

export default async function ApprovalRolesPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref={APPROVAL_ROLES_PATH} />;
  }

  const userEmail = await getUserEmail();
  const canManage = canManageApprovalRoles(context.organization.membershipKind);

  if (!canManage) {
    // Frontend görünürlüğü UX içindir; backend zaten reddeder. Kaynak sızdırmadan güvenli mesaj.
    return (
      <AppShell
        userEmail={userEmail}
        organizationName={context.organization.name}
        activeNav="approval-roles"
        canManage={false}
      >
        <PageHeader title="Onay Rolleri" description="Onay rollerini yönetin." />
        <Alert tone="error">Bu sayfaya erişim yetkiniz yok.</Alert>
      </AppShell>
    );
  }

  const [assignmentsOutcome, membersOutcome] = await Promise.all([
    listApprovalRoleAssignments(context.accessToken, context.organization.organizationId),
    listOrganizationMembers(context.accessToken, context.organization.organizationId),
  ]);

  const failed = assignmentsOutcome.kind !== "ok" || membersOutcome.kind !== "ok";

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="approval-roles"
      canManage
    >
      <PageHeader
        title="Onay Rolleri"
        description="Satın alma taleplerinin hangi kullanıcılar tarafından onaylanacağını yönetin."
      />

      <div className="mb-4">
        <Alert tone="info">
          Rol değişiklikleri yeni oluşturulacak onay görevlerini etkiler. Mevcut açık görevlerin
          ataması korunur.
        </Alert>
      </div>

      {failed ? (
        <div className="flex flex-col items-start gap-3">
          <Alert tone="error">Onay rolleri şu anda getirilemedi. Lütfen tekrar deneyin.</Alert>
          <ButtonLink href={APPROVAL_ROLES_PATH} variant="secondary">
            Tekrar dene
          </ButtonLink>
        </div>
      ) : (
        <ApprovalRoleList
          assignments={assignmentsOutcome.kind === "ok" ? assignmentsOutcome.data : []}
          members={membersOutcome.kind === "ok" ? membersOutcome.data : []}
          actorEmail={userEmail}
          action={assignApprovalRoleAction}
        />
      )}
    </AppShell>
  );
}
