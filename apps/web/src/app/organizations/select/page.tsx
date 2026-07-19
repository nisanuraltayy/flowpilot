import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/auth-card";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { loadOrganizationsForSelection } from "@/features/organizations/context";
import { selectOrganizationAction } from "@/features/organizations/select-actions";
import { SelectOrganizationForm } from "@/features/organizations/select-organization-form";

export const metadata: Metadata = { title: "Organizasyon seç" };

/**
 * Aktif organizasyon seçim ekranı — kullanıcı birden fazla aktif organizasyona
 * üyeyse gösterilir (context çözümü). Hiç org yoksa context onboarding'e yönlendirir.
 */
export default async function SelectOrganizationPage() {
  const loaded = await loadOrganizationsForSelection();
  if (loaded.status === "unavailable") {
    return <ServiceUnavailable retryHref="/organizations/select" />;
  }

  return (
    <AuthCard
      title="Organizasyon seç"
      subtitle="Birden fazla organizasyona üyesin. Devam etmek için birini seç."
    >
      <SelectOrganizationForm
        organizations={loaded.organizations}
        action={selectOrganizationAction}
      />
      <p className="mt-4 text-center text-xs text-slate-500">
        Yeni bir organizasyon mu kuracaksın?{" "}
        <Link href="/onboarding/organization" className="font-medium text-blue-600 underline">
          Organizasyon oluştur
        </Link>
      </p>
    </AuthCard>
  );
}
