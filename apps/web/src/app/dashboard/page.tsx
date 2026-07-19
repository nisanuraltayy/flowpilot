import type { Metadata } from "next";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { CheckIcon, DocumentsIcon, InboxIcon, XIcon } from "@/components/icons";
import { MetricCard } from "@/components/metric-card";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { PurchaseRequestList } from "@/features/purchase-requests/purchase-request-list";
import { getMyTaskInbox, listMyPurchaseRequests } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Genel Bakış" };

/**
 * Satış demosunun ilk ekranı. Sayımlar YALNIZ kullanıcının kendi talep listesinden
 * ve görev kutusundan türetilir — yeni analytics endpoint'i YOK, sahte sayı YOK.
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
  const approved = requests.filter((r) => r.status === "approved").length;
  const rejected = requests.filter((r) => r.status === "rejected").length;
  const recent = requests.slice(0, 5);

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="overview"
    >
      {/* Hero */}
      <section className="mb-6 overflow-hidden rounded-2xl bg-brand-900 px-6 py-7 text-white sm:px-8">
        <p className="text-sm font-medium text-brand-200">{context.organization.name}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Genel Bakış</h1>
        <p className="mt-2 max-w-xl text-sm text-brand-100/90">
          Satın alma taleplerini oluştur, kurala göre yönlendir ve onayları tek yerden,
          denetlenebilir biçimde yürüt.
        </p>
        <div className="mt-5">
          <ButtonLink href="/purchase-requests/new" variant="secondary">
            + Yeni talep oluştur
          </ButtonLink>
        </div>
      </section>

      {/* KPI'lar (gerçek verilerden) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="Taleplerim" value={requests.length} tone="brand" Icon={DocumentsIcon} />
        <MetricCard
          label="Bekleyen onay görevi"
          value={pendingTasks}
          tone={pendingTasks > 0 ? "pending" : "neutral"}
          Icon={InboxIcon}
        />
        <MetricCard label="Onaylanan" value={approved} tone="success" Icon={CheckIcon} />
        <MetricCard label="Reddedilen" value={rejected} tone="danger" Icon={XIcon} />
      </div>

      {/* Onay bekleyen görev uyarısı (sakin) */}
      {pendingTasks > 0 ? (
        <Link
          href="/tasks/inbox"
          className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm transition-colors hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
        >
          <span className="font-medium text-amber-800">
            {pendingTasks} onay görevin karar bekliyor.
          </span>
          <span className="shrink-0 font-semibold text-amber-700">Onay kutusuna git →</span>
        </Link>
      ) : null}

      {/* Son talepler */}
      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Son talepler</h2>
          {recent.length > 0 ? (
            <Link
              href="/purchase-requests"
              className="text-sm font-medium text-brand-600 hover:text-brand-700"
            >
              Tümünü gör
            </Link>
          ) : null}
        </div>
        {recent.length === 0 ? (
          <EmptyState
            title="Henüz satın alma talebin yok"
            description="İlk talebini oluşturarak onay sürecini başlat. Süreç, tutara göre doğru onay zincirini otomatik seçer."
            action={<ButtonLink href="/purchase-requests/new">Yeni talep oluştur</ButtonLink>}
          />
        ) : (
          <PurchaseRequestList items={recent} />
        )}
      </section>
    </AppShell>
  );
}
