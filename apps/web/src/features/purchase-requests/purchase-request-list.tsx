/**
 * "Taleplerim" listesi — actor'ın kendi talepleri, en yeni önce.
 * Durum StatusBadge ile, tutar MoneyDisplay ile; UUID gösterilmez.
 */

import Link from "next/link";

import { MoneyDisplay } from "@/components/money-display";
import { StatusBadge } from "@/components/status-badge";
import { approvalRoleLabel } from "@/features/purchase-requests/display";
import { formatDateTime } from "@/lib/datetime";
import type { PurchaseRequestListItem } from "@/lib/api/resources";

interface PurchaseRequestListProps {
  readonly items: readonly PurchaseRequestListItem[];
}

export function PurchaseRequestList({ items }: PurchaseRequestListProps) {
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => {
        const role = approvalRoleLabel(item.currentApprovalRole);
        return (
          <li key={item.purchaseRequestId}>
            <Link
              href={`/purchase-requests/${item.purchaseRequestId}`}
              className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:flex-row sm:items-center sm:justify-between"
            >
              <span className="flex flex-col gap-1">
                <span className="text-sm font-semibold text-slate-900">{item.title}</span>
                <span className="text-xs text-slate-500">
                  <time dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time>
                  {role ? <span> · Bekleyen adım: {role}</span> : null}
                </span>
              </span>
              <span className="flex items-center gap-3">
                <MoneyDisplay
                  amountMinor={item.amountMinor}
                  className="text-sm font-medium text-slate-900"
                />
                <StatusBadge status={item.status} />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
