/**
 * Üye yönetimi görünürlük kuralları (SAF). Frontend görünürlüğü YALNIZ UX içindir —
 * backend authorization son karar kaynağıdır (bu kuralları bypass etmeye çalışmaz).
 *
 * Kurallar (PRD/handler ile hizalı):
 * - Owner: kendisi dışındaki HERKESİ yönetir; owner/admin/member rol verebilir; başka bir
 *   owner'ı (son owner değilse) düşürebilir; suspend/reactivate/remove yapabilir.
 * - Admin: YALNIZ member hedefleri yönetir; member'ı admin yapabilir; owner rolü VEREMEZ;
 *   owner/admin hedefte işlem yapamaz.
 * - Kimse KENDİ satırında rol/durum değiştiremez (self-mutation engeli).
 * - Removed üyelik terminaldir: hiçbir aksiyon gösterilmez.
 */

export interface MemberTarget {
  readonly email: string | null;
  readonly role: string;
  readonly status: string;
}

export interface MemberRowPermissions {
  /** Hedef, oturum açan kullanıcının kendi satırı mı? */
  readonly isSelf: boolean;
  /** Actor bu hedef üzerinde herhangi bir işlem yapabilir mi? */
  readonly manageable: boolean;
  /** Aksiyon gösterilmiyorsa nedeni (açıklamalı disabled/gizli UX için). */
  readonly reason: "self" | "removed" | "not_permitted" | null;
  /** Seçilebilecek YENİ roller (mevcut rol hariç). */
  readonly roleOptions: readonly string[];
  readonly canSuspend: boolean;
  readonly canReactivate: boolean;
  readonly canRemove: boolean;
}

const NONE = {
  roleOptions: [] as readonly string[],
  canSuspend: false,
  canReactivate: false,
  canRemove: false,
};

/** Actor'ın e-postası, hedefin e-postası ile (büyük/küçük harf duyarsız) eşleşiyor mu? */
function sameUser(actorEmail: string | null, targetEmail: string | null): boolean {
  return (
    actorEmail !== null &&
    targetEmail !== null &&
    actorEmail.trim().toLowerCase() === targetEmail.trim().toLowerCase()
  );
}

export function memberRowPermissions(
  actorRole: string,
  actorEmail: string | null,
  target: MemberTarget,
): MemberRowPermissions {
  if (sameUser(actorEmail, target.email)) {
    return { isSelf: true, manageable: false, reason: "self", ...NONE };
  }
  if (target.status === "removed") {
    return { isSelf: false, manageable: false, reason: "removed", ...NONE };
  }

  const targetManageable =
    actorRole === "owner" || (actorRole === "admin" && target.role === "member");
  if (!targetManageable) {
    return { isSelf: false, manageable: false, reason: "not_permitted", ...NONE };
  }

  const roleOptions =
    actorRole === "owner"
      ? ["owner", "admin", "member"].filter((r) => r !== target.role)
      : // admin: yalnız member hedefi yönetir → member'ı admin'e yükseltebilir (owner veremez).
        target.role === "member"
        ? ["admin"]
        : [];

  return {
    isSelf: false,
    manageable: true,
    reason: null,
    roleOptions,
    canSuspend: target.status === "active",
    canReactivate: target.status === "suspended",
    canRemove: target.status === "active" || target.status === "suspended",
  };
}
