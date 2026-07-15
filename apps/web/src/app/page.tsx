/**
 * Kök sayfa — session durumuna göre yönlendirir.
 *
 * Unauthenticated → /login; authenticated → /onboarding/organization.
 * "Onboarding tamamlandı mı?" bilgisi UYDURULMAZ: kullanıcının
 * organizasyonlarını listeleyen endpoint henüz yoktur; o gelene kadar
 * authenticated kullanıcı onboarding'e gider.
 */

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function RootPage() {
  const supabase = await createClient();

  if (supabase !== null) {
    // Doğrulanmış claims — yalnız session cookie'sinin varlığına güvenilmez.
    const { data } = await supabase.auth.getClaims();
    if (data?.claims != null) {
      redirect("/onboarding/organization");
    }
  }

  redirect("/login");
}
