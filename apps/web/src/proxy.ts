/**
 * Next.js 16 proxy'si (önceki adıyla middleware) — her istekte Supabase
 * session'ını yeniler, korumalı yolları uygular ve nonce tabanlı CSP yazar.
 *
 * CSP akışı (FP-OPS-004A):
 * 1. Her document isteği için YENİ kriptografik nonce üretilir.
 * 2. Politika REQUEST header'ına yazılır — Next.js render katmanı nonce'ı
 *    buradan çıkarıp framework inline script'lerine uygular (Next 16:
 *    `get-script-nonce-from-header`). Mutasyon, mevcut Supabase akışının
 *    `NextResponse.next({ request })` çağrılarıyla render'a taşınır
 *    (cookie güncellemeleriyle aynı kanal).
 * 3. Aynı politika RESPONSE header'ına da yazılır (enforce; Report-Only YOK).
 *    Redirect yanıtlarında header zararsızdır ve auth zinciri değişmez.
 *
 * Nonce loglanmaz, cookie'ye yazılmaz, ayrı bir public header'a konmaz.
 *
 * Muaf tutulanlar (matcher): statik dosyalar, Next iç yolları, favicon ve
 * auth callback — CSP yalnız document response'larında anlamlıdır.
 */

import type { NextRequest } from "next/server";

import { buildContentSecurityPolicy, generateNonce } from "@/lib/csp";
import { updateSession } from "@/lib/supabase/proxy";

const CSP_HEADER = "content-security-policy";

export default async function proxy(request: NextRequest) {
  const policy = buildContentSecurityPolicy({
    nonce: generateNonce(),
    development: process.env.NODE_ENV === "development",
  });

  // Request tarafı: Next render'ı nonce'ı bu header'dan okur.
  request.headers.set(CSP_HEADER, policy);

  const response = await updateSession(request);

  // Response tarafı: browser'a enforce edilen politika — request ile birebir aynı.
  response.headers.set(CSP_HEADER, policy);
  return response;
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
