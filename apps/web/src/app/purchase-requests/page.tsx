import type { Metadata } from "next";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { Alert } from "@/components/alert";
import { EmptyState } from "@/components/empty-state";
import { ServiceUnavailable } from "@/components/service-unavailable";
import {
  getUserEmail,
  requireActiveOrganization,
} from "@/features/organizations/context";
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Taleplerim</h1>
        <Link
          href="/purchase-requests/new"
          className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Yeni talep
        </Link>
      </div>

      <div className="mt-6">
        {outcome.kind !== "ok" ? (
          <Alert tone="error">
            Talepler şu anda getirilemedi. Lütfen sayfayı yenileyin.
          </Alert>
        ) : outcome.data.length === 0 ? (
          <EmptyState
            title="Henüz satın alma talebin yok"
            description="İlk talebini oluşturarak onay sürecini başlatabilirsin."
          />
        ) : (
          <PurchaseRequestList items={outcome.data} />
        )}
      </div>
    </AppShell>
  );
}
