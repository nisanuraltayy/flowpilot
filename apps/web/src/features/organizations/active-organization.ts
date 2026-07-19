/**
 * Aktif organizasyon context'i — SAF karar mantığı (IO/next-headers YOK).
 *
 * Cookie YALNIZ bir organizasyon UUID'si taşır; authorization KAYNAĞI DEĞİLDİR.
 * Her backend isteğinde membership yeniden doğrulanır. Kullanıcı rastgele bir UUID
 * yazsa bile, o UUID actor'ın aktif üyeliklerinde yoksa context çözülmez.
 */

import type { MyOrganization } from "@/lib/api/resources";

export const ACTIVE_ORG_COOKIE = "flowpilot_active_organization";

export type ActiveOrgDecision =
  | { readonly kind: "none" }
  | { readonly kind: "auto"; readonly organization: MyOrganization }
  | { readonly kind: "active"; readonly organization: MyOrganization }
  | { readonly kind: "select"; readonly organizations: readonly MyOrganization[] };

/**
 * Aktif organizasyonu, kullanıcının AKTİF üyelikleri ve cookie'deki org UUID'sinden çözer.
 *
 * - Hiç org yok → `none` (onboarding).
 * - Cookie geçerli bir aktif üyeliğe işaret ediyor → `active`.
 * - Cookie yok/geçersiz + tek org → `auto` (otomatik seç).
 * - Cookie yok/geçersiz + çok org → `select` (seçim ekranı).
 *
 * Cookie'deki UUID artık aktif üyelik değilse YOK SAYILIR (stale cookie temizlenir).
 */
export function decideActiveOrganization(
  organizations: readonly MyOrganization[],
  cookieOrganizationId: string | null,
): ActiveOrgDecision {
  if (organizations.length === 0) {
    return { kind: "none" };
  }
  if (cookieOrganizationId !== null) {
    const match = organizations.find(
      (organization) => organization.organizationId === cookieOrganizationId,
    );
    if (match !== undefined) {
      return { kind: "active", organization: match };
    }
  }
  if (organizations.length === 1) {
    return { kind: "auto", organization: organizations[0] };
  }
  return { kind: "select", organizations };
}

export interface ActiveOrgCookieOptions {
  readonly httpOnly: true;
  readonly sameSite: "lax";
  readonly secure: boolean;
  readonly path: "/";
}

/** Cookie öznitelikleri: HttpOnly, SameSite=Lax, Secure(prod), Path=/. */
export function activeOrgCookieOptions(isProduction: boolean): ActiveOrgCookieOptions {
  return { httpOnly: true, sameSite: "lax", secure: isProduction, path: "/" };
}
