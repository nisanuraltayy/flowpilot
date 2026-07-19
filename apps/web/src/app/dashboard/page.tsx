import type { Metadata } from "next";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { ServiceUnavailable } from "@/components/service-unavailable";
import {
  getUserEmail,
  requireActiveOrganization,
} from "@/features/organizations/context";
import { PurchaseRequestList } from "@/features/purchase-requests/purchase-request-list";
import { getMyTaskInbox, listMyPurchaseRequests } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Genel Bakış" };

const QUICK_LINKS = [
  {
    href: "/purchase-requests/new",
    title: "Yeni satın alma talebi",
    description: "Onaya gidecek yeni bir talep oluştur.",
  },
  {
    href: "/purchase-requests",
    title: "Taleplerim",
    description: "Oluşturduğun taleplerin durumunu izle.",
  },
  {
    href: "/tasks/inbox",
    title: "Onay bekleyen görevler",
    description: "Sana atanmış onay görevlerini gör.",
  },
] as const;

/**
 * Başlangıç ekranı. Sahte KPI ÜRETİLMEZ: sayımlar yalnız kullanıcının kendi
 * talep listesinden ve görev kutusundan türetilir (yeni analytics endpoint'i yok).
 */
export default async function DashboardPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/dashboard" />;
  }

  const userEmail = await getUserEmail();
  const organizationId = context.organization.organizationId;
  const [requestsOutcome, inboxOutcome] = await Promise.all([
    listMyPurchaseRequests(context.accessToken, organizationId),
    getMyTaskInbox(context.accessToken, organizationId),
  ]);

  const requests = requestsOutcome.kind === "ok" ? requestsOutcome.data : [];
  const pendingTasks = inboxOutcome.kind === "ok" ? inboxOutcome.data.length : 0;
  const recent = requests.slice(0, 3);

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="overview"
    >
      <h1 className="text-2xl font-semibold text-slate-900">Genel Bakış</h1>
      <p className="mt-1 text-sm text-slate-600">{context.organization.name}</p>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium text-slate-500">Taleplerim</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">{requests.length}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium text-slate-500">Bekleyen onay görevi</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">{pendingTasks}</p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {QUICK_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <p className="text-sm font-semibold text-slate-900">{link.title}</p>
            <p className="mt-1 text-xs text-slate-500">{link.description}</p>
          </Link>
        ))}
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-slate-900">Son talepler</h2>
        <div className="mt-3">
          {recent.length === 0 ? (
            <EmptyState
              title="Henüz satın alma talebin yok"
              description="İlk talebini oluşturarak onay sürecini başlatabilirsin."
            />
          ) : (
            <PurchaseRequestList items={recent} />
          )}
        </div>
      </section>
    </AppShell>
  );
}
