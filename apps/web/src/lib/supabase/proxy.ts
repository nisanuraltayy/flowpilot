/**
 * Session yenileme + route koruması (Next 16 proxy convention'ı için yardımcı).
 *
 * - Auth cookie'lerini güvenli biçimde yeniler (getAll/setAll toplu API).
 * - Korumalı yollarda DOĞRULANMIŞ CLAIMS kullanır (`auth.getClaims()` —
 *   JWT imzası doğrulanır); yalnız `getSession().user`'a güvenilmez.
 * - Token veya claim içerikleri LOGLANMAZ.
 */

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { getSupabaseConfig } from "@/lib/env";

/** Authentication gerektiren yol önekleri. */
const PROTECTED_PREFIXES = ["/onboarding", "/dashboard"] as const;

/** Oturum açmış kullanıcının görmesi gereksiz auth sayfaları. */
const AUTH_PAGES = ["/login", "/signup"] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function isAuthPage(pathname: string): boolean {
  return AUTH_PAGES.some((page) => pathname === page);
}

export async function updateSession(request: NextRequest): Promise<NextResponse> {
  const config = getSupabaseConfig();
  const { pathname } = request.nextUrl;

  // Supabase yapılandırılmamışsa: login/signup render edilebilir (kontrollü
  // mesaj gösterirler); korumalı sayfalar yine login'e yönlendirilir.
  if (config === null) {
    if (isProtectedPath(pathname)) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }
    return NextResponse.next({ request });
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // Doğrulanmış claims: imza JWKS ile kontrol edilir. Session cookie'sinin
  // varlığı TEK BAŞINA yetki kararı için kullanılmaz.
  const { data } = await supabase.auth.getClaims();
  const isAuthenticated = data?.claims != null;

  if (!isAuthenticated && isProtectedPath(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  if (isAuthenticated && isAuthPage(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/onboarding/organization";
    return NextResponse.redirect(url);
  }

  return response;
}
