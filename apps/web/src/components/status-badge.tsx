/**
 * Durum rozeti — renk TEK BAŞINA anlam taşımaz; metin etiket her zaman görünür.
 */

import {
  purchaseRequestStatusLabel,
  purchaseRequestStatusTone,
  type BadgeTone,
} from "@/features/purchase-requests/display";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "border-green-200 bg-green-50 text-green-800",
  error: "border-red-200 bg-red-50 text-red-800",
  pending: "border-amber-200 bg-amber-50 text-amber-800",
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
};

interface StatusBadgeProps {
  readonly status: string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const tone = purchaseRequestStatusTone(status);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {purchaseRequestStatusLabel(status)}
    </span>
  );
}
