/**
 * "Taleplerim" listesi — masaüstünde temiz tablo, mobilde okunabilir kartlar.
 * Durum StatusBadge, rol RoleBadge, tutar MoneyDisplay ile; UUID gösterilmez.
 * Sayfa yatay taşmaz (tablo kendi kapsayıcısında `overflow-x-auto`).
 */

import Link from "next/link";

import { MoneyDisplay } from "@/components/money-display";
import { RoleBadge } from "@/components/role-badge";
import { StatusBadge } from "@/components/status-badge";
import { formatDateTime } from "@/lib/datetime";
import type { PurchaseRequestListItem } from "@/lib/api/resources";

interface PurchaseRequestListProps {
  readonly items: readonly PurchaseRequestListItem[];
}

export function PurchaseRequestList({ items }: PurchaseRequestListProps) {
  return (
    <>
      {/* Masaüstü: tablo */}
      <div className="hidden overflow-hidden rounded-xl border border-slate-200 bg-white sm:block">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3">Talep</th>
                <th scope="col" className="px-4 py-3">Tutar</th>
                <th scope="col" className="px-4 py-3">Durum</th>
                <th scope="col" className="px-4 py-3">Bekleyen adım</th>
                <th scope="col" className="px-4 py-3">Oluşturuldu</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Detay</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => (
                <tr key={item.purchaseRequestId} className="transition-colors hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-900">{item.title}</td>
                  <td className="px-4 py-3 text-slate-700">
                    <MoneyDisplay amountMinor={item.amountMinor} />
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                  <td className="px-4 py-3">
                    <RoleBadge role={item.currentApprovalRole} /> {item.currentApprovalRole === null ? <span className="text-slate-400">—</span> : null}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    <time dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/purchase-requests/${item.purchaseRequestId}`}
                      className="font-medium text-brand-600 hover:text-brand-700"
                    >
                      Detay
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobil: kartlar */}
      <ul className="flex flex-col gap-3 sm:hidden">
        {items.map((item) => (
          <li key={item.purchaseRequestId}>
            <Link
              href={`/purchase-requests/${item.purchaseRequestId}`}
              className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-brand-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-semibold text-slate-900">{item.title}</span>
                <StatusBadge status={item.status} />
              </div>
              <div className="flex items-center justify-between gap-3">
                <MoneyDisplay amountMinor={item.amountMinor} className="text-sm font-medium text-slate-900" />
                <RoleBadge role={item.currentApprovalRole} />
              </div>
              <time dateTime={item.createdAt} className="text-xs text-slate-500">
                {formatDateTime(item.createdAt)}
              </time>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
