import type { Metadata } from "next";

import { AuthCard } from "@/components/auth-card";
import { signInAction } from "@/features/auth/actions";
import { LoginForm } from "@/features/auth/login-form";
import { sanitizeInternalPath } from "@/lib/redirect";

export const metadata: Metadata = { title: "Giriş yap" };

interface LoginPageProps {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const rawNext = params.next;
  // Yalnız uygulama-içi relative path korunur (open-redirect koruması); geçersizse yok sayılır.
  const nextRaw = typeof rawNext === "string" ? rawNext : null;
  const sanitized = sanitizeInternalPath(nextRaw, "");
  const next = sanitized === "" ? undefined : sanitized;

  return (
    <AuthCard
      title="Giriş yap"
      subtitle="FlowPilot hesabınla devam et — talepler kaybolmaz, onaylar dağılmaz."
    >
      <LoginForm action={signInAction} next={next} />
    </AuthCard>
  );
}
