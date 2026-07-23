/**
 * Onay rolü yönetimi görünürlük kuralları (SAF). Backend policy TEK karar kaynağıdır
 * (APPROVAL_ROLE_ASSIGNMENT_READ/CHANGE → owner/admin; member yasak). Frontend yalnız UX
 * görünürlüğü sağlar ve backend'i bypass etmeye çalışmaz.
 *
 * Aday uygunluğu: onay rolüne YALNIZ aktif organizasyon üyeleri atanabilir (suspended/removed
 * atanamaz — backend 409). Bir kullanıcı birden fazla onay rolü taşıyabilir (backend destekler),
 * bu yüzden frontend başka rol taşıyor diye adayı ELEMEZ.
 */

import { isOrgManagerRole } from "@/features/organizations/roles";
import type { MemberListItem } from "@/lib/api/resources";

/** owner/admin onay rollerini yönetebilir (backend policy ile birebir). */
export function canManageApprovalRoles(actorRole: string): boolean {
  return isOrgManagerRole(actorRole);
}

/** Onay rolüne atanabilecek adaylar: yalnız AKTİF üyeler. */
export function eligibleApprovalCandidates(
  members: readonly MemberListItem[],
): readonly MemberListItem[] {
  return members.filter((m) => m.status === "active");
}
