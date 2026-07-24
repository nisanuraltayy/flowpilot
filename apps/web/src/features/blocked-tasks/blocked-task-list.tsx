"use client";

/**
 * Engellenen onay görevleri listesi — kart düzeni (dar ekranda taşmaz). Backend'in sağladığı
 * güvenli alanlar gösterilir; talep başlığı/e-posta backend'den GELMEZ, bu yüzden talep sahibi
 * e-postası (mevcutsa) üye listesinden eşlenir, talep referansı kısa ID olarak gösterilir.
 * Hassas identity (provider_subject/auth/JWT) GÖSTERİLMEZ.
 */

import { formatDateTime } from "@/lib/datetime";
import type { ResolveBlockedTaskAction } from "@/features/blocked-tasks/action-types";
import { blockedReasonDescription, blockedReasonLabel, taskStatusLabel } from "@/features/blocked-tasks/display";
import { ResolveBlockedTaskModal } from "@/features/blocked-tasks/resolve-blocked-task-modal";
import { approvalRoleLabel } from "@/features/approval-roles/display";
import { memberEmailLabel } from "@/features/members/display";
import type { BlockedApprovalTask, MemberListItem } from "@/lib/api/resources";

interface BlockedTaskListProps {
  readonly tasks: readonly BlockedApprovalTask[];
  readonly members: readonly MemberListItem[];
  readonly action: ResolveBlockedTaskAction;
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

export function BlockedTaskList({ tasks, members, action }: BlockedTaskListProps) {
  const emailByUserId = new Map(members.map((m) => [m.userId, m.email] as const));

  return (
    <ul className="flex flex-col gap-3">
      {tasks.map((task) => {
        const requesterEmail =
          task.requesterUserId !== null && emailByUserId.has(task.requesterUserId)
            ? memberEmailLabel(emailByUserId.get(task.requesterUserId) ?? null)
            : "Bilinmiyor";
        return (
          <li
            key={task.taskId}
            className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5"
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {approvalRoleLabel(task.approverRole)}
                  </h3>
                  <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                    {taskStatusLabel(task.status)}
                  </span>
                </div>
                <p className="text-sm font-medium text-slate-700">
                  {blockedReasonLabel(task.blockedReason)}
                </p>
                <p className="max-w-2xl text-xs text-slate-500">
                  {blockedReasonDescription(task.blockedReason)}
                </p>
              </div>
              <div className="shrink-0">
                <ResolveBlockedTaskModal
                  taskId={task.taskId}
                  approverRole={task.approverRole}
                  blockedReason={task.blockedReason}
                  action={action}
                />
              </div>
            </div>

            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
              <div className="flex justify-between gap-3 sm:justify-start">
                <dt className="text-slate-500">Talep sahibi</dt>
                <dd className="truncate font-medium text-slate-700" title={requesterEmail}>
                  {requesterEmail}
                </dd>
              </div>
              <div className="flex justify-between gap-3 sm:justify-start">
                <dt className="text-slate-500">Talep</dt>
                <dd className="font-mono text-slate-600">
                  {task.purchaseRequestId !== null ? shortId(task.purchaseRequestId) : "—"}
                </dd>
              </div>
              <div className="flex justify-between gap-3 sm:justify-start">
                <dt className="text-slate-500">Oluşturulma</dt>
                <dd className="text-slate-600">{formatDateTime(task.createdAt)}</dd>
              </div>
              <div className="flex justify-between gap-3 sm:justify-start">
                <dt className="text-slate-500">Güncellenme</dt>
                <dd className="text-slate-600">{formatDateTime(task.updatedAt)}</dd>
              </div>
            </dl>
          </li>
        );
      })}
    </ul>
  );
}
