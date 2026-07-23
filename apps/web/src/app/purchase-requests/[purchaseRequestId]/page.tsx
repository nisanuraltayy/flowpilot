import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { MoneyDisplay } from "@/components/money-display";
import { RoleBadge } from "@/components/role-badge";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { StatusBadge } from "@/components/status-badge";
import { Timeline } from "@/components/timeline";
import { WorkflowRail } from "@/components/workflow-rail";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { isOrgManagerRole } from "@/features/organizations/roles";
import { buildProcessSteps } from "@/features/purchase-requests/workflow-view";
import { formatDateTime } from "@/lib/datetime";
import { getPurchaseRequest, getPurchaseRequestTimeline } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Talep detayı" };

interface PageProps {
  readonly params: Promise<{ readonly purchaseRequestId: string }>;
}

function ResultBanner({ status }: { readonly status: string }) {
  if (status === "approved") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-800">
        <span aria-hidden="true">✓</span> Talep onaylandı; süreç tamamlandı.
      </div>
    );
  }
  if (status === "rejected") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">
        <span aria-hidden="true">✕</span> Talep reddedildi; süreç sonlandı.
      </div>
    );
  }
  return null;
}

export default async function PurchaseRequestDetailPage({ params }: PageProps) {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/purchase-requests" />;
  }
  const { purchaseRequestId } = await params;
  const userEmail = await getUserEmail();
  const organizationId = context.organization.organizationId;

  const [detailOutcome, timelineOutcome] = await Promise.all([
    getPurchaseRequest(context.accessToken, organizationId, purchaseRequestId),
    getPurchaseRequestTimeline(context.accessToken, organizationId, purchaseRequestId),
  ]);

  if (detailOutcome.kind === "not_found") {
    notFound();
  }
  if (detailOutcome.kind !== "ok") {
    return <ServiceUnavailable retryHref={`/purchase-requests/${purchaseRequestId}`} />;
  }

  const detail = detailOutcome.data;
  const timeline = timelineOutcome.kind === "ok" ? timelineOutcome.data : [];
  const processSteps = buildProcessSteps(timeline);

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="requests"
      canManage={isOrgManagerRole(context.organization.membershipKind)}
    >
      <div className="mx-auto max-w-3xl">
        <Link
          href="/purchase-requests"
          className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          ← Taleplerim
        </Link>

        {/* Özet */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">
              {detail.title}
            </h1>
            <StatusBadge status={detail.status} />
          </div>

          <dl className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium text-slate-500">Tutar</dt>
              <dd className="mt-0.5 text-lg font-semibold text-slate-900">
                <MoneyDisplay amountMinor={detail.amountMinor} />
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-slate-500">Bekleyen onay adımı</dt>
              <dd className="mt-0.5 text-sm text-slate-900">
                <RoleBadge role={detail.currentApprovalRole} />
                {detail.currentApprovalRole === null ? (
                  <span className="text-slate-400">—</span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-slate-500">Oluşturuldu</dt>
              <dd className="mt-0.5 text-sm text-slate-700">
                <time dateTime={detail.createdAt}>{formatDateTime(detail.createdAt)}</time>
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-slate-500">Güncellendi</dt>
              <dd className="mt-0.5 text-sm text-slate-700">
                <time dateTime={detail.updatedAt}>{formatDateTime(detail.updatedAt)}</time>
              </dd>
            </div>
            {detail.description ? (
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-slate-500">Açıklama</dt>
                <dd className="mt-0.5 whitespace-pre-wrap text-sm text-slate-700">
                  {detail.description}
                </dd>
              </div>
            ) : null}
          </dl>

          <div className="mt-5">
            <ResultBanner status={detail.status} />
          </div>
        </div>

        {/* Süreç akışı (özet rail — timeline'dan türetilir) */}
        {processSteps.length > 1 ? (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <h2 className="mb-4 text-sm font-semibold text-slate-900">Onay akışı</h2>
            <WorkflowRail steps={processSteps} ariaLabel="Talebin onay akışı" />
          </section>
        ) : null}

        {/* Süreç zaman çizelgesi (kronolojik detay) */}
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Zaman çizelgesi</h2>
          <Timeline items={timeline} />
        </section>
      </div>
    </AppShell>
  );
}
