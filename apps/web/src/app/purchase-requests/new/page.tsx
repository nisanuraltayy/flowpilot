import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ServiceUnavailable } from "@/components/service-unavailable";
import {
  getUserEmail,
  requireActiveOrganization,
} from "@/features/organizations/context";
import { createPurchaseRequestAction } from "@/features/purchase-requests/actions";
import { PurchaseRequestForm } from "@/features/purchase-requests/purchase-request-form";

export const metadata: Metadata = { title: "Yeni satın alma talebi" };

export default async function NewPurchaseRequestPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref="/purchase-requests/new" />;
  }
  const userEmail = await getUserEmail();

  return (
    <AppShell userEmail={userEmail} organizationName={context.organization.name} activeNav="new">
      <div className="mx-auto max-w-xl">
        <h1 className="text-2xl font-semibold text-slate-900">Yeni satın alma talebi</h1>
        <p className="mt-1 text-sm text-slate-600">
          Talep, tutara göre otomatik olarak doğru onay zincirine yönlendirilir.
        </p>
        <div className="mt-6">
          <PurchaseRequestForm action={createPurchaseRequestAction} />
        </div>
      </div>
    </AppShell>
  );
}
