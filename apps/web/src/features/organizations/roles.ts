/**
 * Organizasyon yönetişim rolü yardımcıları (SAF).
 *
 * Frontend görünürlüğü YALNIZ UX içindir — backend authorization kaynak olmaya devam eder.
 * Yönetim (davet/üye) yalnız owner/admin'e gösterilir; member için gizlenir.
 */

const MANAGER_ROLES: ReadonlySet<string> = new Set(["owner", "admin"]);

export function isOrgManagerRole(membershipKind: string): boolean {
  return MANAGER_ROLES.has(membershipKind);
}
