import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { MoneyDisplay } from "@/components/money-display";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { StatusBadge } from "@/components/status-badge";
import { Timeline } from "@/components/timeline";
import {
  getUserEmail,
  requireActiveOrganization,
} from "@/features/organizations/context";
import { approvalRoleLabel } from "@/features/purchase-requests/display";
import { formatDateTime } from "@/lib/datetime";
import { getPurchaseRequest, getPurchaseRequestTimeline } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Talep detayı" };

interface PageProps {
  readonly params: Promise<{ readonly purchaseRequestId: string }>;
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
  const role = approvalRoleLabel(detail.currentApprovalRole);
  const timeline = timelineOutcome.kind === "ok" ? timelineOutcome.data : [];

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="requests"
    >
      <div className="mx-auto max-w-2xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">{detail.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              Oluşturuldu: <time dateTime={detail.createdAt}>{formatDateTime(detail.createdAt)}</time>
            </p>
          </div>
          <StatusBadge status={detail.status} />
        </div>

        <dl className="mt-6 grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium text-slate-500">Tutar</dt>
            <dd className="mt-0.5 text-sm font-semibold text-slate-900">
              <MoneyDisplay amountMinor={detail.amountMinor} />
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-slate-500">Bekleyen onay adımı</dt>
            <dd className="mt-0.5 text-sm text-slate-900">{role ?? "—"}</dd>
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

        <section className="mt-8">
          <h2 className="text-sm font-semibold text-slate-900">Süreç zaman çizelgesi</h2>
          <div className="mt-3">
            <Timeline items={timeline} />
          </div>
        </section>
      </div>
    </AppShell>
  );
}
