/** Engellenen görev görüntüleme yardımcıları — gerçek reason + güvenli fallback. */

import { describe, expect, it } from "vitest";

import {
  blockedReasonDescription,
  blockedReasonLabel,
  taskStatusLabel,
} from "@/features/blocked-tasks/display";

describe("blockedReasonLabel / description", () => {
  it("self_approval_no_eligible_assignee için özel metin", () => {
    expect(blockedReasonLabel("self_approval_no_eligible_assignee")).toBe(
      "Kendi talebini onaylama engeli",
    );
    expect(blockedReasonDescription("self_approval_no_eligible_assignee")).toMatch(
      /talebi oluşturan kişi/i,
    );
  });

  it("null ve bilinmeyen reason güvenli fallback kullanır", () => {
    expect(blockedReasonLabel(null)).toBe("Atama sorunu");
    expect(blockedReasonLabel("weird_reason")).toBe("Atama sorunu");
    expect(blockedReasonDescription(null)).toMatch(/ilerleyemiyor/i);
    expect(blockedReasonDescription("weird_reason")).toMatch(/ilerleyemiyor/i);
  });
});

describe("taskStatusLabel", () => {
  it("bilinen durumları etiketler; bilinmeyen ham kalır", () => {
    expect(taskStatusLabel("blocked")).toBe("Engellendi");
    expect(taskStatusLabel("active")).toBe("Aktif");
    expect(taskStatusLabel("pending")).toBe("Bekliyor");
    expect(taskStatusLabel("???")).toBe("???");
  });
});
