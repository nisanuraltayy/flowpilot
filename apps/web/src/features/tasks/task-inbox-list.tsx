/**
 * Kişisel onay kutusu — YALNIZ backend'in döndürdüğü (current actor'a atanmış) görevler.
 * Her görev için karar formu (approve/reject) gömülüdür.
 */

import Link from "next/link";

import { MoneyDisplay } from "@/components/money-display";
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
      {items.map((item) => (
        <li
          key={item.taskId}
          className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-1">
              <Link
                href={`/purchase-requests/${item.purchaseRequestId}`}
                className="text-sm font-semibold text-blue-700 underline-offset-2 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {item.purchaseRequestTitle}
              </Link>
              <span className="text-xs text-slate-500">
                Gereken onay: {approvalRoleLabel(item.requiredRole) ?? item.requiredRole} ·{" "}
                <time dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time>
              </span>
            </div>
            <MoneyDisplay
              amountMinor={item.amountMinor}
              className="text-sm font-medium text-slate-900"
            />
          </div>
          <ApprovalDecisionForm taskId={item.taskId} action={decideApprovalTaskAction} />
        </li>
      ))}
    </ul>
  );
}
