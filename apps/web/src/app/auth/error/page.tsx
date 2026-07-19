import type { Metadata } from "next";
import Link from "next/link";

import { Alert } from "@/components/alert";
import { AuthCard } from "@/components/auth-card";

export const metadata: Metadata = { title: "Giriş hatası" };

/** Auth hata ekranı — teknik detay SIZDIRMAZ. */
export default function AuthErrorPage() {
  return (
    <AuthCard title="Bir sorun oluştu">
      <div className="flex flex-col gap-4">
        <Alert tone="error">
          Giriş bağlantısı doğrulanamadı. Bağlantının süresi dolmuş veya daha önce
          kullanılmış olabilir.
        </Alert>
        <Link
          href="/login"
          className="inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
        >
          Giriş sayfasına dön
        </Link>
      </div>
    </AuthCard>
  );
}
