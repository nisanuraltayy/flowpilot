/**
 * Süreç türetme testleri — adımlar YALNIZ gerçek timeline/status'tan çıkar; uydurma yok.
 */

import { describe, expect, it } from "vitest";

import {
  buildProcessSteps,
  processStatusChip,
} from "@/features/purchase-requests/workflow-view";
import type { TimelineItem } from "@/lib/api/resources";

function evt(eventType: string, roleKey: string | null = null): TimelineItem {
  return {
    eventType,
    occurredAt: "2026-07-19T09:00:00Z",
    actorIsCurrentUser: false,
    roleKey,
    taskId: null,
    message: "",
  };
}

describe("buildProcessSteps", () => {
  it("tamamlanan iki adımlı akışı türetir: Talep → roller (completed) → Onaylandı", () => {
    const steps = buildProcessSteps([
      evt("purchase_request.created"),
      evt("workflow.started"),
      evt("approval.task_assigned", "team_manager"),
      evt("approval.approved", "team_manager"),
      evt("approval.task_assigned", "finance"),
      evt("approval.approved", "finance"),
      evt("workflow.completed"),
    ]);
    expect(steps.map((s) => [s.label, s.state])).toEqual([
      ["Talep", "completed"],
      ["Ekip yöneticisi", "completed"],
      ["Finans", "completed"],
      ["Onaylandı", "completed"],
    ]);
  });

  it("devam eden akışta mevcut rol 'active', sonuç 'upcoming' olur", () => {
    const steps = buildProcessSteps([
      evt("purchase_request.created"),
      evt("workflow.started"),
      evt("approval.task_assigned", "team_manager"),
      evt("approval.approved", "team_manager"),
      evt("approval.task_assigned", "finance"),
    ]);
    expect(steps.map((s) => [s.label, s.state])).toEqual([
      ["Talep", "completed"],
      ["Ekip yöneticisi", "completed"],
      ["Finans", "active"],
      ["Sonuç", "upcoming"],
    ]);
  });

  it("ret akışında rol 'rejected', sonuç 'rejected' olur; gelecek rol uydurulmaz", () => {
    const steps = buildProcessSteps([
      evt("purchase_request.created"),
      evt("workflow.started"),
      evt("approval.task_assigned", "team_manager"),
      evt("approval.rejected", "team_manager"),
      evt("workflow.rejected"),
    ]);
    expect(steps.map((s) => [s.label, s.state])).toEqual([
      ["Talep", "completed"],
      ["Ekip yöneticisi", "rejected"],
      ["Reddedildi", "rejected"],
    ]);
  });
});

describe("processStatusChip", () => {
  it("approved → tamamlandı, rejected → sonlandırıldı", () => {
    expect(processStatusChip("approved", null)).toEqual({
      label: "Süreç tamamlandı",
      state: "completed",
    });
    expect(processStatusChip("rejected", null)).toEqual({
      label: "Süreç sonlandırıldı",
      state: "rejected",
    });
  });

  it("in_approval → mevcut rolün onayında (active)", () => {
    expect(processStatusChip("in_approval", "finance")).toEqual({
      label: "Finans onayında",
      state: "active",
    });
  });

  it("draft → Taslak; bilinmeyen status ham + upcoming", () => {
    expect(processStatusChip("draft", null)).toEqual({ label: "Taslak", state: "upcoming" });
    expect(processStatusChip("weird", null)).toEqual({ label: "weird", state: "upcoming" });
  });
});
