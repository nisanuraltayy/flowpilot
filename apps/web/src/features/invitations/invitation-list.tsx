"use client";

/**
 * Davet listesi — masaüstünde tablo, mobilde yatay kaydırma (erişilebilir <th scope>).
 * Durum rozeti + rol etiketi metinle gösterilir; yalnız bekleyen davetlerde iptal butonu.
 *
 * NOT: Backend listesi bugün yalnız `pending` (süresi dolmamış) davetleri döndürür; diğer
 * durumlar için de etiket/rozet hazırdır (ileri uyum). Ham token liste verisinde YOKTUR.
 */

import { formatDateTime } from "@/lib/datetime";
import type { RevokeInvitationResult } from "@/features/invitations/actions";
import { invitationRoleLabel, isInvitationRevocable } from "@/features/invitations/display";
import { InvitationStatusBadge } from "@/features/invitations/invitation-status-badge";
import { RevokeInvitationButton } from "@/features/invitations/revoke-invitation-button";
import type { InvitationListItem } from "@/lib/api/resources";

interface InvitationListProps {
  readonly items: readonly InvitationListItem[];
  readonly revokeAction: (
    previous: RevokeInvitationResult,
    formData: FormData,
  ) => Promise<RevokeInvitationResult>;
}

export function InvitationList({ items, revokeAction }: InvitationListProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full min-w-[36rem] border-collapse text-sm">
        <caption className="sr-only">Bekleyen davetler</caption>
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <th scope="col" className="px-4 py-2.5 font-medium">
              E-posta
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Rol
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Durum
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Oluşturulma
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Son geçerlilik
            </th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">
              İşlem
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.invitationId} className="border-b border-slate-100 last:border-0">
              <td className="max-w-[16rem] truncate px-4 py-3 font-medium text-slate-900" title={item.invitedEmail}>
                {item.invitedEmail}
              </td>
              <td className="px-4 py-3 text-slate-700">{invitationRoleLabel(item.role)}</td>
              <td className="px-4 py-3">
                <InvitationStatusBadge status={item.status} />
              </td>
              <td className="px-4 py-3 text-slate-600">{formatDateTime(item.createdAt)}</td>
              <td className="px-4 py-3 text-slate-600">{formatDateTime(item.expiresAt)}</td>
              <td className="px-4 py-3 text-right">
                {isInvitationRevocable(item.status) ? (
                  <RevokeInvitationButton
                    invitationId={item.invitationId}
                    invitedEmail={item.invitedEmail}
                    action={revokeAction}
                  />
                ) : (
                  <span className="text-xs text-slate-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
