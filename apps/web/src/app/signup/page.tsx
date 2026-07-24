import type { Metadata } from "next";

import { AuthCard } from "@/components/auth-card";
import { signUpAction } from "@/features/auth/actions";
import { SignupForm } from "@/features/auth/signup-form";

// Nonce tabanlı CSP (FP-OPS-004A): bu sayfa build'de prerender edilirse inline
// hydration script'leri nonce'suz kalır ve enforce edilen politika onları
// bloklar. Bu yüzden request-time render zorunludur.
export const dynamic = "force-dynamic";


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
