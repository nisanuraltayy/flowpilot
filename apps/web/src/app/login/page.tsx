import type { Metadata } from "next";

import { AuthCard } from "@/components/auth-card";
import { signInAction } from "@/features/auth/actions";
import { LoginForm } from "@/features/auth/login-form";

export const metadata: Metadata = { title: "Giriş yap" };

export default function LoginPage() {
  return (
    <AuthCard
      title="Giriş yap"
      subtitle="FlowPilot hesabınla devam et — talepler kaybolmaz, onaylar dağılmaz."
    >
      <LoginForm action={signInAction} />
    </AuthCard>
  );
}
