/**
 * Engellenen görev yönetimi görünürlüğü (SAF). Backend policy TEK karar kaynağıdır
 * (APPROVAL_BLOCKED_TASK_READ/RESOLVE → owner/admin; member yasak). Frontend yalnız UX
 * görünürlüğü sağlar ve backend'i bypass etmeye çalışmaz.
 */

import { isOrgManagerRole } from "@/features/organizations/roles";

/** owner/admin engellenen görevleri görüp çözebilir (backend policy ile birebir). */
export function canManageBlockedTasks(actorRole: string): boolean {
  return isOrgManagerRole(actorRole);
}
