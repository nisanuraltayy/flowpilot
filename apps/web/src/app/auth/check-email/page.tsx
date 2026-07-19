import type { Metadata } from "next";
import Link from "next/link";

import { Alert } from "@/components/alert";
import { AuthCard } from "@/components/auth-card";

export const metadata: Metadata = { title: "E-postanı kontrol et" };

/**
 * E-posta doğrulama bekleme ekranı. Kullanıcının sistemde var olup olmadığını
 * DOĞRULAYAN hiçbir bilgi gösterilmez — herkes aynı ekranı görür.
 */
export default function CheckEmailPage() {
  return (
    <AuthCard title="E-postanı kontrol et">
      <div className="flex flex-col gap-4">
        <Alert tone="info">
          Kayıt isteğin alındı. Eğer bu e-posta ile devam edilebiliyorsa, gelen
          kutunda bir doğrulama bağlantısı bulacaksın. Bağlantıya tıklayarak
          hesabını etkinleştirebilirsin.
        </Alert>
        <p className="text-sm text-slate-500">
          E-posta birkaç dakika içinde gelmezse spam klasörünü kontrol et.
        </p>
        <Link
          href="/login"
          className="text-center text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          Giriş sayfasına dön
        </Link>
      </div>
    </AuthCard>
  );
}
