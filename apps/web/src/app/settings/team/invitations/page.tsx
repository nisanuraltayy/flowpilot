import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { createInvitationAction, revokeInvitationAction } from "@/features/invitations/actions";
import { CreateInvitationForm } from "@/features/invitations/create-invitation-form";
import { InvitationList } from "@/features/invitations/invitation-list";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { isOrgManagerRole } from "@/features/organizations/roles";
import { listInvitations } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Davetler" };

export default async function InvitationsPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/settings/team/invitations" />;
  }

  const userEmail = await getUserEmail();
  const canManage = isOrgManagerRole(context.organization.membershipKind);

  if (!canManage) {
    // Frontend görünürlüğü UX içindir; backend zaten reddeder. Kaynak sızdırmadan güvenli mesaj.
    return (
      <AppShell
        userEmail={userEmail}
        organizationName={context.organization.name}
        activeNav="invitations"
        canManage={false}
      >
        <PageHeader title="Davetler" description="Ekip davetlerini yönetin." />
        <Alert tone="error">Bu sayfaya erişim yetkiniz yok.</Alert>
      </AppShell>
    );
  }

  const outcome = await listInvitations(
    context.accessToken,
    context.organization.organizationId,
  );

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="invitations"
      canManage
    >
      <PageHeader
        title="Davetler"
        description="Organizasyonuna yeni üye davet et, bekleyen davetleri gör ve gerektiğinde iptal et."
      />

      <div className="flex flex-col gap-6">
        <section aria-labelledby="new-invitation-heading">
          <h2 id="new-invitation-heading" className="mb-2 text-sm font-semibold text-slate-800">
            Yeni davet
          </h2>
          <CreateInvitationForm action={createInvitationAction} />
        </section>

        <section aria-labelledby="pending-invitations-heading">
          <h2
            id="pending-invitations-heading"
            className="mb-2 text-sm font-semibold text-slate-800"
          >
            Bekleyen davetler
          </h2>
          {outcome.kind !== "ok" ? (
            <Alert tone="error">Davetler şu anda getirilemedi. Lütfen sayfayı yenileyin.</Alert>
          ) : outcome.data.length === 0 ? (
            <EmptyState
              title="Bekleyen davet yok"
              description="Yukarıdaki formdan e-posta ile yeni bir davet oluşturabilirsin."
              icon="✉️"
            />
          ) : (
            <InvitationList items={outcome.data} revokeAction={revokeInvitationAction} />
          )}
        </section>
      </div>
    </AppShell>
  );
}
