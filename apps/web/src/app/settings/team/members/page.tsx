import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { changeMemberRoleAction, setMemberStatusAction } from "@/features/members/actions";
import { MemberList } from "@/features/members/member-list";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { isOrgManagerRole } from "@/features/organizations/roles";
import { listOrganizationMembers } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Üyeler" };

const MEMBERS_PATH = "/settings/team/members";

export default async function MembersPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref={MEMBERS_PATH} />;
  }

  const userEmail = await getUserEmail();
  const canManage = isOrgManagerRole(context.organization.membershipKind);

  if (!canManage) {
    // Frontend görünürlüğü UX içindir; backend zaten reddeder. Kaynak sızdırmadan güvenli mesaj.
    return (
      <AppShell
        userEmail={userEmail}
        organizationName={context.organization.name}
        activeNav="members"
        canManage={false}
      >
        <PageHeader title="Üyeler" description="Organizasyon üyelerini yönetin." />
        <Alert tone="error">Bu sayfaya erişim yetkiniz yok.</Alert>
      </AppShell>
    );
  }

  const outcome = await listOrganizationMembers(
    context.accessToken,
    context.organization.organizationId,
  );

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="members"
      canManage
    >
      <PageHeader
        title="Üyeler"
        description="Organizasyon üyelerini görüntüle, rollerini değiştir, askıya al veya üyeliği kaldır."
      />

      {outcome.kind !== "ok" ? (
        <div className="flex flex-col items-start gap-3">
          <Alert tone="error">Üyeler şu anda getirilemedi. Lütfen tekrar deneyin.</Alert>
          <ButtonLink href={MEMBERS_PATH} variant="secondary">
            Tekrar dene
          </ButtonLink>
        </div>
      ) : outcome.data.length === 0 ? (
        <EmptyState
          title="Üye yok"
          description="Bu organizasyonda görüntülenecek üye bulunmuyor."
          icon="👥"
        />
      ) : (
        <MemberList
          members={outcome.data}
          actorRole={context.organization.membershipKind}
          actorEmail={userEmail}
          roleAction={changeMemberRoleAction}
          statusAction={setMemberStatusAction}
        />
      )}
    </AppShell>
  );
}
