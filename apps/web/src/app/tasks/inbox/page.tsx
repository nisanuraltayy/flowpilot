import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { TaskInboxList } from "@/features/tasks/task-inbox-list";
import { getMyTaskInbox } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Onay Kutusu" };

export default async function TaskInboxPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/tasks/inbox" />;
  }
  const userEmail = await getUserEmail();
  const outcome = await getMyTaskInbox(context.accessToken, context.organization.organizationId);
  const count = outcome.kind === "ok" ? outcome.data.length : 0;

  return (
    <AppShell userEmail={userEmail} organizationName={context.organization.name} activeNav="inbox">
      <PageHeader
        title="Onay Kutusu"
        description={
          count > 0
            ? `${count} görev kararını bekliyor.`
            : "Sana atanmış, karar bekleyen onay görevleri burada görünür."
        }
      />

      {outcome.kind !== "ok" ? (
        <Alert tone="error">Görevler şu anda getirilemedi. Lütfen sayfayı yenileyin.</Alert>
      ) : outcome.data.length === 0 ? (
        <EmptyState
          icon="✅"
          title="Bekleyen onay görevin yok"
          description="Sana bir onay görevi atandığında burada görünecek ve buradan onaylayıp reddedebileceksin."
          action={<ButtonLink href="/purchase-requests">Taleplerime git</ButtonLink>}
        />
      ) : (
        <TaskInboxList items={outcome.data} />
      )}
    </AppShell>
  );
}
