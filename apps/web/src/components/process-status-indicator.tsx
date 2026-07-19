/**
 * Liste/kart için kompakt süreç göstergesi: küçük workflow düğümü + metin.
 * Durum yalnız renkle değil düğüm ikonu + metinle anlaşılır.
 */

import { WorkflowNode } from "@/components/workflow-rail";
import type { ProcessStatusChip } from "@/features/purchase-requests/workflow-view";

const TEXT: Record<ProcessStatusChip["state"], string> = {
  completed: "text-green-700",
  active: "text-amber-700",
  upcoming: "text-slate-500",
  rejected: "text-red-700",
};

export function ProcessStatusIndicator({ chip }: { readonly chip: ProcessStatusChip }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <WorkflowNode state={chip.state} className="h-5 w-5" />
      <span className={`text-xs font-medium ${TEXT[chip.state]}`}>{chip.label}</span>
    </span>
  );
}
