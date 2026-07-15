/**
 * Next.js 16 proxy'si (önceki adıyla middleware) — her istekte Supabase
 * session'ını yeniler ve korumalı yolları uygular.
 *
 * Muaf tutulanlar: statik dosyalar, Next iç yolları, favicon ve auth callback.
 */

import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/proxy";

export default async function proxy(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Şunlar DIŞINDA tüm istekler:
     * - _next/static, _next/image (statik varlıklar)
     * - favicon ve yaygın görsel dosyaları
     * - auth/callback (code exchange kendi route handler'ında yapılır)
     */
    "/((?!_next/static|_next/image|favicon.ico|auth/callback|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
