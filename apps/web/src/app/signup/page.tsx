import type { Metadata } from "next";

import { AuthCard } from "@/components/auth-card";
import { signUpAction } from "@/features/auth/actions";
import { SignupForm } from "@/features/auth/signup-form";

export const metadata: Metadata = { title: "Kayıt ol" };

export default function SignupPage() {
  return (
    <AuthCard
      title="Hesap oluştur"
      subtitle="Birkaç dakika içinde şirketinin taleplerini ve onaylarını tek yerden yönet."
    >
      <SignupForm action={signUpAction} />
    </AuthCard>
  );
}
