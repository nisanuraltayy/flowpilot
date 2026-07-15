import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";
import { EmptyState } from "@/components/empty-state";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Panel" };

/**
 * Minimal authenticated shell — SAHTE organizasyon listesi, istatistik veya
 * workflow verisi GÖSTERİLMEZ. Gerçek business verisi sonraki aşamada
 * (purchase request dikey dilimi) gelecektir.
 */
export default async function DashboardPage() {
  const supabase = await createClient();
  let userEmail: string | null = null;
  if (supabase !== null) {
    const { data } = await supabase.auth.getClaims();
    const email = data?.claims?.email;
    userEmail = typeof email === "string" ? email : null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader userEmail={userEmail} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <h1 className="text-2xl font-semibold text-slate-900">Hoş geldin 👋</h1>
        <p className="mt-1 text-sm text-slate-600">
          Organizasyon kurulumun tamamlandı. FlowPilot&apos;u kullanmaya hazırsın.
        </p>
        <div className="mt-8">
          <EmptyState
            title="Henüz satın alma talebi yok"
            description="Satın alma talepleri, koşullu yönlendirme ve sıralı onay akışı sonraki aşamada eklenecek. İlk talebini o zaman buradan oluşturabileceksin."
          />
        </div>
      </main>
    </div>
  );
}
