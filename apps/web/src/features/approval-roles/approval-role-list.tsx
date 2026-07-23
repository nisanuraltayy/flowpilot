"use client";

/**
 * Onay rolleri listesi — 3 sabit rol (team_manager/finance/general_manager) için kart.
 * Her kart: rol adı + açıklama + mevcut atanan kullanıcı (veya "atanmadı") + ata/değiştir.
 * Removed/suspended üyeler aday DEĞİLDİR (yalnız aktif üyeler). Hassas identity gösterilmez.
 */

import Link from "next/link";

import { ButtonLink } from "@/components/button";
import type { AssignApprovalRoleAction } from "@/features/approval-roles/action-types";
import { AssignApprovalRoleModal } from "@/features/approval-roles/assign-approval-role-modal";
import {
  APPROVAL_ROLE_KEYS,
  approvalRoleDescription,
  approvalRoleLabel,
} from "@/features/approval-roles/display";
import { eligibleApprovalCandidates } from "@/features/approval-roles/permissions";
import { memberEmailLabel } from "@/features/members/display";
import type { ApprovalRoleAssignment, MemberListItem } from "@/lib/api/resources";

interface ApprovalRoleListProps {
  readonly assignments: readonly ApprovalRoleAssignment[];
  readonly members: readonly MemberListItem[];
  readonly actorEmail: string | null;
  readonly action: AssignApprovalRoleAction;
}

export function ApprovalRoleList({ assignments, members, actorEmail, action }: ApprovalRoleListProps) {
  const byRole = new Map(assignments.map((a) => [a.roleKey, a] as const));
  const candidates = eligibleApprovalCandidates(members);
  const hasCandidates = candidates.length > 0;

  return (
    <div className="flex flex-col gap-4">
      {!hasCandidates ? (
        <div className="flex flex-col items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-800">
            Onay rolüne atanabilecek aktif bir üye bulunmuyor.
          </p>
          <ButtonLink href="/settings/team/members" variant="secondary" size="sm">
            Üyeleri yönet
          </ButtonLink>
        </div>
      ) : null}

      <ul className="flex flex-col gap-3">
        {APPROVAL_ROLE_KEYS.map((roleKey) => {
          const assignment = byRole.get(roleKey) ?? null;
          const assigned = assignment !== null;
          return (
            <li
              key={roleKey}
              className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"
            >
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold text-slate-900">
                  {approvalRoleLabel(roleKey)}
                </h3>
                <p className="text-xs text-slate-500">{approvalRoleDescription(roleKey)}</p>
                <p className="mt-1 text-sm">
                  {assigned ? (
                    <span className="font-medium text-slate-800">
                      {memberEmailLabel(assignment.assignedUserEmail)}
                    </span>
                  ) : (
                    <span className="text-slate-500">Henüz kullanıcı atanmadı.</span>
                  )}
                </p>
              </div>

              <div className="shrink-0">
                {hasCandidates ? (
                  <AssignApprovalRoleModal
                    roleKey={roleKey}
                    roleLabel={approvalRoleLabel(roleKey)}
                    triggerLabel={assigned ? "Değiştir" : "Ata"}
                    successMessage={
                      assigned ? "Onay rolü ataması güncellendi." : "Onay rolüne kullanıcı atandı."
                    }
                    currentAssigneeId={assignment?.assignedUserId ?? null}
                    currentVersion={assignment?.version ?? null}
                    candidates={candidates}
                    actorEmail={actorEmail}
                    action={action}
                  />
                ) : (
                  <span className="text-xs text-slate-400">
                    <Link href="/settings/team/members" className="underline hover:text-slate-600">
                      Aktif üye ekleyin
                    </Link>
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
