/**
 * Kişisel onay kutusu — YALNIZ backend'in döndürdüğü (current actor'a atanmış) görevler.
 * Her kart bir AKIŞIN AKTİF ADIMI gibi görünür: "Sıra sende" bağlamı + aktif düğüm +
 * talep özeti + karar formu. Yeni backend verisi uydurulmaz; yalnız görevin rolü gösterilir.
 */

import Link from "next/link";

import { MoneyDisplay } from "@/components/money-display";
import { WorkflowNode } from "@/components/workflow-rail";
import { approvalRoleLabel } from "@/features/purchase-requests/display";
import { decideApprovalTaskAction } from "@/features/tasks/actions";
import { ApprovalDecisionForm } from "@/features/tasks/approval-decision-form";
import { formatDateTime } from "@/lib/datetime";
import type { InboxItem } from "@/lib/api/resources";

interface TaskInboxListProps {
  readonly items: readonly InboxItem[];
}

export function TaskInboxList({ items }: TaskInboxListProps) {
  return (
    <ul className="flex flex-col gap-4">
      {items.map((item) => {
        const roleLabel = approvalRoleLabel(item.requiredRole) ?? item.requiredRole;
        return (
          <li
            key={item.taskId}
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
          >
            {/* Aktif adım bağlamı */}
            <div className="flex items-center gap-2 border-b border-amber-100 bg-amber-50 px-4 py-2 sm:px-5">
              <WorkflowNode state="active" className="h-5 w-5" />
              <span className="text-xs font-semibold text-amber-800">
                Sıra sende — {roleLabel} onayı
              </span>
            </div>

            <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
              <div className="flex min-w-0 flex-col gap-1">
                <Link
                  href={`/purchase-requests/${item.purchaseRequestId}`}
                  className="truncate text-base font-semibold text-slate-900 hover:text-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {item.purchaseRequestTitle}
                </Link>
                <time dateTime={item.createdAt} className="text-xs text-slate-500">
                  Atandı: {formatDateTime(item.createdAt)}
                </time>
              </div>
              <MoneyDisplay
                amountMinor={item.amountMinor}
                className="text-base font-semibold text-slate-900"
              />
            </div>

            <div className="bg-slate-50/60 p-4 sm:p-5">
              <ApprovalDecisionForm taskId={item.taskId} action={decideApprovalTaskAction} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
