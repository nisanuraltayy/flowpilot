"use client";

/**
 * Üye listesi — client-side arama + rol/durum filtresi (backend sırasını korur; deterministik).
 * Masaüstünde tablo, dar ekranda yatay kaydırma (erişilebilir <th scope>). Removed üyeler
 * durumlarıyla listede kalır. Hassas identity (provider_subject/auth/JWT) GÖSTERİLMEZ.
 */

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { formatDateTime } from "@/lib/datetime";
import type { ChangeRoleAction, SetStatusAction } from "@/features/members/action-types";
import { memberEmailLabel, memberRoleLabel } from "@/features/members/display";
import { MemberRowActions } from "@/features/members/member-row-actions";
import { MemberStatusBadge } from "@/features/members/member-status-badge";
import { memberRowPermissions } from "@/features/members/permissions";
import type { MemberListItem } from "@/lib/api/resources";

interface MemberListProps {
  readonly members: readonly MemberListItem[];
  readonly actorRole: string;
  readonly actorEmail: string | null;
  readonly roleAction: ChangeRoleAction;
  readonly statusAction: SetStatusAction;
}

const ROLE_FILTERS = ["all", "owner", "admin", "member"] as const;
const STATUS_FILTERS = ["all", "active", "suspended", "removed"] as const;

const ROLE_FILTER_LABELS: Record<(typeof ROLE_FILTERS)[number], string> = {
  all: "Tüm roller",
  owner: "Sahip",
  admin: "Yönetici",
  member: "Üye",
};
const STATUS_FILTER_LABELS: Record<(typeof STATUS_FILTERS)[number], string> = {
  all: "Tüm durumlar",
  active: "Aktif",
  suspended: "Askıya alındı",
  removed: "Kaldırıldı",
};

export function MemberList({ members, actorRole, actorEmail, roleAction, statusAction }: MemberListProps) {
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<(typeof ROLE_FILTERS)[number]>("all");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const filtered = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("tr");
    // Backend sırası korunur; filtre yalnız daraltır (deterministik).
    return members.filter((m) => {
      if (roleFilter !== "all" && m.role !== roleFilter) return false;
      if (statusFilter !== "all" && m.status !== statusFilter) return false;
      if (q !== "" && !(m.email ?? "").toLocaleLowerCase("tr").includes(q)) return false;
      return true;
    });
  }, [members, search, roleFilter, statusFilter]);

  const selectClass =
    "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <p className="text-sm text-slate-600" aria-live="polite">
          {filtered.length === members.length
            ? `${members.length} üye`
            : `${filtered.length} / ${members.length} üye`}
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="flex flex-col gap-1">
            <label htmlFor="member-search" className="sr-only">
              E-posta ara
            </label>
            <input
              id="member-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="E-posta ara"
              className={selectClass}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="member-role-filter" className="sr-only">
              Role göre filtrele
            </label>
            <select
              id="member-role-filter"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value as (typeof ROLE_FILTERS)[number])}
              className={selectClass}
            >
              {ROLE_FILTERS.map((r) => (
                <option key={r} value={r}>
                  {ROLE_FILTER_LABELS[r]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="member-status-filter" className="sr-only">
              Duruma göre filtrele
            </label>
            <select
              id="member-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as (typeof STATUS_FILTERS)[number])}
              className={selectClass}
            >
              {STATUS_FILTERS.map((s) => (
                <option key={s} value={s}>
                  {STATUS_FILTER_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="Filtreye uygun üye yok"
          description="Arama veya filtreleri değiştirerek tekrar deneyin."
          icon="🔍"
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <caption className="sr-only">Organizasyon üyeleri</caption>
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
                  Güncellenme
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">
                  İşlemler
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((member) => {
                const permissions = memberRowPermissions(actorRole, actorEmail, member);
                return (
                  <tr key={member.membershipId} className="border-b border-slate-100 last:border-0">
                    <td
                      className="max-w-[18rem] truncate px-4 py-3 font-medium text-slate-900"
                      title={member.email ?? undefined}
                    >
                      {memberEmailLabel(member.email)}
                      {permissions.isSelf ? (
                        <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-500">
                          Siz
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{memberRoleLabel(member.role)}</td>
                    <td className="px-4 py-3">
                      <MemberStatusBadge status={member.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(member.createdAt)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(member.updatedAt)}</td>
                    <td className="px-4 py-3 text-right">
                      <MemberRowActions
                        member={member}
                        permissions={permissions}
                        roleAction={roleAction}
                        statusAction={statusAction}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
