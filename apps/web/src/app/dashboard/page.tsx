import type { Metadata } from "next";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { CheckIcon, DocumentsIcon, InboxIcon, XIcon } from "@/components/icons";
import { MetricCard } from "@/components/metric-card";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { WorkflowRail, type WorkflowStepData } from "@/components/workflow-rail";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { PurchaseRequestList } from "@/features/purchase-requests/purchase-request-list";
import { getMyTaskInbox, listMyPurchaseRequests } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Genel Bakış" };

/** Hero'daki DEKORATİF örnek akış (gerçek veri/sonuç değil — yalnız görsel dil). */
const EXAMPLE_FLOW: readonly WorkflowStepData[] = [
  { key: "req", label: "Talep", state: "completed" },
  { key: "tm", label: "Ekip yöneticisi", state: "completed" },
  { key: "fin", label: "Finans", state: "active" },
  { key: "res", label: "Sonuç", sublabel: "Bekliyor", state: "upcoming" },
];

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
      {/* Hero — açık, premium yüzey (yoğun mor blok değil) */}
      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 lg:p-7">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-md">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Genel Bakış</h1>
            <p className="mt-1.5 text-sm text-slate-600">
              Talepleri kurala göre yönlendir, onayları adım adım ve denetlenebilir biçimde yürüt.
            </p>
            <div className="mt-4">
              <ButtonLink href="/purchase-requests/new">+ Yeni talep oluştur</ButtonLink>
            </div>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4 lg:w-80 lg:shrink-0">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">
              Örnek onay akışı
            </p>
            <WorkflowRail steps={EXAMPLE_FLOW} ariaLabel="Örnek onay akışı" />
          </div>
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
