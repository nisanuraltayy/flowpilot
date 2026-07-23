"use client";

/**
 * Bir üye satırının yönetim aksiyonları (owner/admin görünürlüğüne göre).
 *
 * Görünürlük UX içindir; backend authorization son karardır. Self satır ve removed üyelikte
 * aksiyon gösterilmez (açıklamalı). Rol seçenekleri kullanıcının veremeyeceği rolleri içermez.
 */

import { MemberMutationModal } from "@/features/members/member-mutation-modal";
import { memberEmailLabel, memberRoleLabel } from "@/features/members/display";
import type { MemberRowPermissions } from "@/features/members/permissions";
import type { ChangeRoleAction, SetStatusAction } from "@/features/members/action-types";
import type { MemberListItem } from "@/lib/api/resources";

interface MemberRowActionsProps {
  readonly member: MemberListItem;
  readonly permissions: MemberRowPermissions;
  readonly roleAction: ChangeRoleAction;
  readonly statusAction: SetStatusAction;
}

export function MemberRowActions({
  member,
  permissions,
  roleAction,
  statusAction,
}: MemberRowActionsProps) {
  if (!permissions.manageable) {
    const note =
      permissions.reason === "self"
        ? "Kendi hesabınız"
        : permissions.reason === "removed"
          ? "Kaldırıldı"
          : "—";
    return <span className="text-xs text-slate-400">{note}</span>;
  }

  const email = memberEmailLabel(member.email);

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {permissions.roleOptions.length > 0 ? (
        <MemberMutationModal
          triggerLabel="Rol değiştir"
          triggerVariant="secondary"
          title="Üyenin rolünü değiştir"
          confirmLabel="Rolü güncelle"
          pendingLabel="Güncelleniyor…"
          confirmVariant="primary"
          successMessage="Üyenin rolü güncellendi."
          duplicateMessage="Üye zaten bu role sahip; değişiklik yapılmadı."
          targetUserId={member.userId}
          expectedVersion={member.version}
          action={roleAction}
        >
          <div className="flex flex-col gap-1.5">
            <p className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{email}</span> için yeni rol seçin.
            </p>
            <label
              htmlFor={`role-${member.userId}`}
              className="text-sm font-medium text-slate-700"
            >
              Yeni rol
            </label>
            <select
              id={`role-${member.userId}`}
              name="role"
              defaultValue={permissions.roleOptions[0]}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            >
              {permissions.roleOptions.map((role) => (
                <option key={role} value={role}>
                  {memberRoleLabel(role)}
                </option>
              ))}
            </select>
          </div>
        </MemberMutationModal>
      ) : null}

      {permissions.canSuspend ? (
        <MemberMutationModal
          triggerLabel="Askıya al"
          triggerVariant="secondary"
          title="Üyeyi askıya al"
          confirmLabel="Evet, askıya al"
          pendingLabel="Askıya alınıyor…"
          confirmVariant="danger"
          successMessage="Üye askıya alındı."
          duplicateMessage="Üye zaten askıda; değişiklik yapılmadı."
          targetUserId={member.userId}
          expectedVersion={member.version}
          status="suspended"
          action={statusAction}
        >
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">{email}</span> askıya alınacak. Bu işlem
            kullanıcının oturumunu ve yetkilerini etkileyebilir. Üyelik fiziksel olarak silinmez ve
            daha sonra yeniden aktifleştirilebilir.
          </p>
        </MemberMutationModal>
      ) : null}

      {permissions.canReactivate ? (
        <MemberMutationModal
          triggerLabel="Yeniden aktifleştir"
          triggerVariant="secondary"
          title="Üyeyi yeniden aktifleştir"
          confirmLabel="Evet, aktifleştir"
          pendingLabel="Aktifleştiriliyor…"
          confirmVariant="success"
          successMessage="Üye yeniden aktifleştirildi."
          duplicateMessage="Üye zaten aktif; değişiklik yapılmadı."
          targetUserId={member.userId}
          expectedVersion={member.version}
          status="active"
          action={statusAction}
        >
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">{email}</span> yeniden aktifleştirilecek ve
            organizasyon erişimi geri verilecek.
          </p>
        </MemberMutationModal>
      ) : null}

      {permissions.canRemove ? (
        <MemberMutationModal
          triggerLabel="Üyeliği kaldır"
          triggerVariant="danger"
          title="Üyeliği kaldır"
          confirmLabel="Evet, kaldır"
          pendingLabel="Kaldırılıyor…"
          confirmVariant="danger"
          successMessage="Üyelik kaldırıldı."
          duplicateMessage="Üyelik zaten kaldırılmış; değişiklik yapılmadı."
          targetUserId={member.userId}
          expectedVersion={member.version}
          status="removed"
          action={statusAction}
        >
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">{email}</span> üyeliği kaldırılacak. Bu
            işlem kalıcı bir üyelik durumu oluşturur: satır listede kalır ancak{" "}
            <span className="font-medium">“Kaldırıldı” durumu terminaldir</span> — üye yeniden
            aktifleştirilemez. Yeniden katılım için gelecekte ayrı bir davet/işlem gerekir.
          </p>
        </MemberMutationModal>
      ) : null}
    </div>
  );
}
