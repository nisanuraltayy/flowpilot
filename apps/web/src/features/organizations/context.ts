import "server-only";

/**
 * Aktif organizasyon context'i — SERVER-SIDE IO (session token + cookie + yönlendirme).
 *
 * Token yalnız burada okunur ve API client'a iletilir; browser'a taşınmaz. Cookie
 * authorization DEĞİLDİR — her istekte backend membership'i yeniden doğrular
 * (listMyOrganizations actor-scoped RLS ile).
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ACTIVE_ORG_COOKIE,
  activeOrgCookieOptions,
  decideActiveOrganization,
} from "@/features/organizations/active-organization";
import { listMyOrganizations, type MyOrganization } from "@/lib/api/resources";
import { createClient } from "@/lib/supabase/server";

export type OrganizationContext =
  | { readonly status: "ok"; readonly organization: MyOrganization; readonly accessToken: string }
  | { readonly status: "unavailable" };

/** Doğrulanmış oturumun access token'ı; yoksa null. */
export async function getServerAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  if (supabase === null) {
    return null;
  }
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

/** Doğrulanmış kullanıcının e-postası (üst çubukta gösterim için); yoksa null. */
export async function getUserEmail(): Promise<string | null> {
  const supabase = await createClient();
  if (supabase === null) {
    return null;
  }
  const { data } = await supabase.auth.getClaims();
  const email = data?.claims?.email;
  return typeof email === "string" ? email : null;
}

/** Aktif organizasyon cookie'sindeki UUID (yoksa null). */
export async function readActiveOrganizationCookie(): Promise<string | null> {
  const store = await cookies();
  return store.get(ACTIVE_ORG_COOKIE)?.value ?? null;
}

/** Aktif organizasyonu cookie'ye yazar (YALNIZ server action / route handler'da çağrılabilir). */
export async function writeActiveOrganizationCookie(organizationId: string): Promise<void> {
  const store = await cookies();
  store.set(
    ACTIVE_ORG_COOKIE,
    organizationId,
    activeOrgCookieOptions(process.env.NODE_ENV === "production"),
  );
}

/** Aktif organizasyon cookie'sini temizler (YALNIZ server action / route handler'da). */
export async function clearActiveOrganizationCookie(): Promise<void> {
  const store = await cookies();
  store.delete(ACTIVE_ORG_COOKIE);
}

/**
 * Kullanıcının AKTİF organizasyonlarını getirir. Oturum yoksa `/login`'e yönlendirir.
 * API erişilemezse `unavailable` döner (sayfa güvenli hata gösterir).
 */
async function loadOrganizations(): Promise<
  | { readonly status: "ok"; readonly organizations: readonly MyOrganization[]; readonly accessToken: string }
  | { readonly status: "unavailable" }
> {
  const accessToken = await getServerAccessToken();
  if (accessToken === null) {
    redirect("/login");
  }
  const outcome = await listMyOrganizations(accessToken);
  if (outcome.kind === "unauthorized") {
    redirect("/login");
  }
  if (outcome.kind !== "ok") {
    return { status: "unavailable" };
  }
  return { status: "ok", organizations: outcome.data, accessToken };
}

/**
 * Korumalı sayfalar için aktif organizasyonu ZORUNLU kılar.
 *
 * - Hiç org yok → `/onboarding/organization`.
 * - Cookie yok/geçersiz + çok org → `/organizations/select`.
 * - Aksi hâlde aktif org + token döner.
 */
export async function requireActiveOrganization(): Promise<OrganizationContext> {
  const loaded = await loadOrganizations();
  if (loaded.status === "unavailable") {
    return { status: "unavailable" };
  }
  const cookieOrganizationId = await readActiveOrganizationCookie();
  const decision = decideActiveOrganization(loaded.organizations, cookieOrganizationId);

  if (decision.kind === "none") {
    redirect("/onboarding/organization");
  }
  if (decision.kind === "select") {
    redirect("/organizations/select");
  }
  // "auto" (tek org, cookie yok) ya da "active" (cookie geçerli).
  return {
    status: "ok",
    organization: decision.organization,
    accessToken: loaded.accessToken,
  };
}

/** Seçim ekranı için: tüm aktif organizasyonlar (veya unavailable). */
export async function loadOrganizationsForSelection(): Promise<
  | { readonly status: "ok"; readonly organizations: readonly MyOrganization[] }
  | { readonly status: "unavailable" }
> {
  const loaded = await loadOrganizations();
  if (loaded.status === "unavailable") {
    return { status: "unavailable" };
  }
  if (loaded.organizations.length === 0) {
    redirect("/onboarding/organization");
  }
  return { status: "ok", organizations: loaded.organizations };
}
