import type { Metadata } from "next";

import { AuthCard } from "@/components/auth-card";
import { createOrganizationAction } from "@/features/organizations/actions";
import { OrganizationForm } from "@/features/organizations/organization-form";

export const metadata: Metadata = { title: "Şirketini oluştur" };

/**
 * Organization onboarding — korumalı route (proxy unauthenticated kullanıcıyı
 * /login'e yönlendirir).
 */
export default function OrganizationOnboardingPage() {
  return (
    <AuthCard
      title="Şirketini oluştur"
      subtitle="FlowPilot; satın alma taleplerini, onayları ve iş akışlarını şirketinin çatısı altında toplar. Önce organizasyonunu oluşturalım — sen otomatik olarak sahibi (owner) olacaksın."
    >
      <OrganizationForm action={createOrganizationAction} />
    </AuthCard>
  );
}
