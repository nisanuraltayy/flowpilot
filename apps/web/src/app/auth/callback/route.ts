/**
 * Supabase auth callback'i — authorization code'u güvenli biçimde session'a
 * çevirir.
 *
 * - Open redirect YOKTUR: hedef yol sanitize edilir, yalnız uygulama içi yollar.
 * - Code veya token LOGLANMAZ.
 * - Hatalı/eksik code → kontrollü /auth/error sayfası.
 */

import { NextResponse, type NextRequest } from "next/server";

import { sanitizeInternalPath } from "@/lib/redirect";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeInternalPath(searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    if (supabase !== null) {
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (!error) {
        return NextResponse.redirect(`${origin}${next}`);
      }
    }
  }

  return NextResponse.redirect(`${origin}/auth/error`);
}
