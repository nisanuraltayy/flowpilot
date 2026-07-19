/**
 * Kişisel onay kutusu — YALNIZ backend'in döndürdüğü (current actor'a atanmış) görevler.
 * Her görev bir kart; talep özeti + karar formu (approve/reject) gömülü.
 */

import Link from "next/link";

import { MoneyDisplay } from "@/components/money-display";
import { RoleBadge } from "@/components/role-badge";
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
          className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
            <div className="flex min-w-0 flex-col gap-1.5">
              <Link
                href={`/purchase-requests/${item.purchaseRequestId}`}
                className="truncate text-base font-semibold text-slate-900 hover:text-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {item.purchaseRequestTitle}
              </Link>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <RoleBadge role={item.requiredRole} prefix="Gereken:" />
                {approvalRoleLabel(item.requiredRole) === null ? (
                  <span>Gereken onay: {item.requiredRole}</span>
                ) : null}
                <span aria-hidden="true">·</span>
                <time dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time>
              </div>
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
      ))}
    </ul>
  );
}
