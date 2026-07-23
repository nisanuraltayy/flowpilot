/**
 * Üye durum rozeti — renk TEK BAŞINA anlam taşımaz; metin etiket her zaman görünür.
 */

import { memberStatusLabel, memberStatusTone, type BadgeTone } from "@/features/members/display";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "border-green-200 bg-green-50 text-green-800",
  error: "border-red-200 bg-red-50 text-red-800",
  pending: "border-amber-200 bg-amber-50 text-amber-800",
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
};

interface MemberStatusBadgeProps {
  readonly status: string;
}

export function MemberStatusBadge({ status }: MemberStatusBadgeProps) {
  const tone = memberStatusTone(status);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {memberStatusLabel(status)}
    </span>
  );
}
