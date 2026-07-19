/**
 * Dashboard KPI kartı — YALNIZ gerçek mevcut verilerden beslenir (sahte sayı yok).
 * Değer + etiket her zaman metin; ton yalnız renkle değil, etiketle de anlaşılır.
 */

import type { ComponentType } from "react";

export type MetricTone = "neutral" | "brand" | "success" | "pending" | "danger";

const VALUE_TONE: Record<MetricTone, string> = {
  neutral: "text-slate-900",
  brand: "text-brand-700",
  success: "text-green-700",
  pending: "text-amber-700",
  danger: "text-red-700",
};

const ICON_TONE: Record<MetricTone, string> = {
  neutral: "bg-slate-100 text-slate-500",
  brand: "bg-brand-50 text-brand-600",
  success: "bg-green-50 text-green-600",
  pending: "bg-amber-50 text-amber-600",
  danger: "bg-red-50 text-red-600",
};

interface MetricCardProps {
  readonly label: string;
  readonly value: number | string;
  readonly tone?: MetricTone;
  readonly Icon?: ComponentType<{ readonly className?: string }>;
}

export function MetricCard({ label, value, tone = "neutral", Icon }: MetricCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {Icon ? (
        <span
          aria-hidden="true"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${ICON_TONE[tone]}`}
        >
          <Icon className="h-5 w-5" />
        </span>
      ) : null}
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-slate-500">{label}</p>
        <p className={`mt-0.5 text-2xl font-semibold ${VALUE_TONE[tone]}`}>{value}</p>
      </div>
    </div>
  );
}
