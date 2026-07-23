/** Onay rolü görüntüleme yardımcıları — TR etiket/açıklama + güvenli fallback + sıra. */

import { describe, expect, it } from "vitest";

import {
  APPROVAL_ROLE_KEYS,
  approvalRoleDescription,
  approvalRoleLabel,
} from "@/features/approval-roles/display";

describe("approvalRoleLabel", () => {
  it("backend role_key → Türkçe; bilinmeyen ham kalır", () => {
    expect(approvalRoleLabel("team_manager")).toBe("Takım Yöneticisi");
    expect(approvalRoleLabel("finance")).toBe("Finans Sorumlusu");
    expect(approvalRoleLabel("general_manager")).toBe("Genel Müdür");
    expect(approvalRoleLabel("weird_role")).toBe("weird_role");
  });
});

describe("approvalRoleDescription", () => {
  it("bilinen roller için açıklama döner; bilinmeyende boş", () => {
    expect(approvalRoleDescription("team_manager")).toMatch(/ilk onayı/i);
    expect(approvalRoleDescription("finance")).toMatch(/finansal uygunluk/i);
    expect(approvalRoleDescription("general_manager")).toMatch(/son onay/i);
    expect(approvalRoleDescription("weird_role")).toBe("");
  });
});

describe("APPROVAL_ROLE_KEYS", () => {
  it("backend sırasını korur: team_manager → finance → general_manager", () => {
    expect(APPROVAL_ROLE_KEYS).toEqual(["team_manager", "finance", "general_manager"]);
  });
});
