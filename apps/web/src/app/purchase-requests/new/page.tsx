import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { createPurchaseRequestAction } from "@/features/purchase-requests/actions";
import { PurchaseRequestForm } from "@/features/purchase-requests/purchase-request-form";

export const metadata: Metadata = { title: "Yeni satın alma talebi" };

const CHAIN = [
  { range: "10.000 ₺ altı", roles: "Ekip yöneticisi" },
  { range: "10.000 – 50.000 ₺", roles: "Ekip yöneticisi + Finans" },
  { range: "50.000 ₺ üzeri", roles: "Ekip yöneticisi + Finans + Genel müdür" },
] as const;

export default async function NewPurchaseRequestPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/purchase-requests/new" />;
  }
  const userEmail = await getUserEmail();

  return (
    <AppShell userEmail={userEmail} organizationName={context.organization.name} activeNav="new">
      <PageHeader
        title="Yeni satın alma talebi"
        description="Talep, tutara göre doğru onay zincirine otomatik yönlendirilir."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <PurchaseRequestForm action={createPurchaseRequestAction} />
          </div>
        </div>

        <aside className="lg:col-span-1">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">Onay süreci nasıl çalışır?</h2>
            <p className="mt-1 text-xs text-slate-500">
              Onay zinciri girdiğin tutara göre otomatik belirlenir.
            </p>
            <ul className="mt-4 flex flex-col gap-3">
              {CHAIN.map((step) => (
                <li key={step.range} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p className="text-xs font-semibold text-brand-700">{step.range}</p>
                  <p className="mt-0.5 text-sm text-slate-700">{step.roles}</p>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-slate-400">
              Bu yalnızca bilgilendirme amaçlıdır; gerçek karar süreç tanımında saklanır.
            </p>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
