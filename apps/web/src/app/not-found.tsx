import Link from "next/link";

import { ButtonLink } from "@/components/button";
import { FlowPilotLogo } from "@/components/flowpilot-logo";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-4 text-center">
      <FlowPilotLogo />
      <p className="text-5xl font-bold tracking-tight text-brand-600">404</p>
      <h1 className="text-lg font-semibold text-slate-900">Sayfa bulunamadı</h1>
      <p className="max-w-sm text-sm text-slate-600">
        Aradığın kaynak bulunamadı veya erişim yetkin yok. Panele dönüp devam edebilirsin.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <ButtonLink href="/dashboard">Panele dön</ButtonLink>
        <Link href="/purchase-requests" className="text-sm font-medium text-brand-600 hover:text-brand-700">
          Taleplerim
        </Link>
      </div>
    </main>
  );
}
