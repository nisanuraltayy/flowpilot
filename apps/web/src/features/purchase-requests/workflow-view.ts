/**
 * Süreç görselleştirme türetmeleri — SAF. YALNIZ backend'in gerçekten döndürdüğü
 * alanlardan (timeline event'leri / status / current_approval_role) üretilir;
 * geçmiş/gelecek rol zinciri UYDURULMAZ.
 */

import type { WorkflowStepData, WorkflowStepState } from "@/components/workflow-rail";
import { approvalRoleLabel } from "@/features/purchase-requests/display";
import type { TimelineItem } from "@/lib/api/resources";

/**
 * Talep detay timeline'ından gerçek süreç adımlarını çıkarır:
 * Talep → (her onay rolü, gerçek durumuyla) → Sonuç.
 */
export function buildProcessSteps(timeline: readonly TimelineItem[]): WorkflowStepData[] {
  const steps: WorkflowStepData[] = [{ key: "start", label: "Talep", state: "completed" }];

  const order: string[] = [];
  const roleState = new Map<string, WorkflowStepState>();
  const ensure = (role: string): void => {
    if (!roleState.has(role)) {
      order.push(role);
      roleState.set(role, "active");
    }
  };

  for (const item of timeline) {
    if (item.roleKey === null) {
      continue;
    }
    if (item.eventType === "approval.task_assigned") {
      ensure(item.roleKey);
    } else if (item.eventType === "approval.approved") {
      ensure(item.roleKey);
      roleState.set(item.roleKey, "completed");
    } else if (item.eventType === "approval.rejected") {
      ensure(item.roleKey);
      roleState.set(item.roleKey, "rejected");
    }
  }

  for (const role of order) {
    steps.push({
      key: role,
      label: approvalRoleLabel(role) ?? role,
      state: roleState.get(role) ?? "upcoming",
    });
  }

  const completed = timeline.some((i) => i.eventType === "workflow.completed");
  const rejected = timeline.some((i) => i.eventType === "workflow.rejected");
  steps.push({
    key: "result",
    label: completed ? "Onaylandı" : rejected ? "Reddedildi" : "Sonuç",
    sublabel: completed || rejected ? undefined : "Bekliyor",
    state: completed ? "completed" : rejected ? "rejected" : "upcoming",
  });

  return steps;
}

export interface ProcessStatusChip {
  readonly label: string;
  readonly state: WorkflowStepState;
}

/**
 * Liste satırı için güvenli, kompakt süreç göstergesi. Yalnız `status` +
 * `current_approval_role`'dan türetilir (tam zincir uydurulmaz).
 */
export function processStatusChip(
  status: string,
  currentApprovalRole: string | null,
): ProcessStatusChip {
  if (status === "approved") {
    return { label: "Süreç tamamlandı", state: "completed" };
  }
  if (status === "rejected") {
    return { label: "Süreç sonlandırıldı", state: "rejected" };
  }
  if (status === "in_approval") {
    const role = approvalRoleLabel(currentApprovalRole);
    return { label: role ? `${role} onayında` : "Onay sürüyor", state: "active" };
  }
  if (status === "draft") {
    return { label: "Taslak", state: "upcoming" };
  }
  return { label: status, state: "upcoming" };
}
