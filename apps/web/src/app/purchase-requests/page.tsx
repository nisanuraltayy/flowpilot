import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { PurchaseRequestList } from "@/features/purchase-requests/purchase-request-list";
import { listMyPurchaseRequests } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Taleplerim" };

export default async function PurchaseRequestsPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/purchase-requests" />;
  }
  const userEmail = await getUserEmail();
  const outcome = await listMyPurchaseRequests(
    context.accessToken,
    context.organization.organizationId,
  );

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="requests"
    >
      <PageHeader
        title="Taleplerim"
        description="Oluşturduğun satın alma talepleri ve güncel onay durumları."
        action={<ButtonLink href="/purchase-requests/new">+ Yeni talep</ButtonLink>}
      />

      {outcome.kind !== "ok" ? (
        <Alert tone="error">Talepler şu anda getirilemedi. Lütfen sayfayı yenileyin.</Alert>
      ) : outcome.data.length === 0 ? (
        <EmptyState
          title="Henüz satın alma talebin yok"
          description="İlk talebini oluşturarak onay sürecini başlatabilirsin."
          action={<ButtonLink href="/purchase-requests/new">Yeni talep oluştur</ButtonLink>}
        />
      ) : (
        <PurchaseRequestList items={outcome.data} />
      )}
    </AppShell>
  );
}
