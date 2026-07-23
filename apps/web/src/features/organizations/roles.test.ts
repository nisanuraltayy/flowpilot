/** Organizasyon yönetişim rolü — frontend görünürlük yardımcısı (UX-only). */

import { describe, expect, it } from "vitest";

import { isOrgManagerRole } from "@/features/organizations/roles";

describe("isOrgManagerRole", () => {
  it("owner ve admin yönetici sayılır", () => {
    expect(isOrgManagerRole("owner")).toBe(true);
    expect(isOrgManagerRole("admin")).toBe(true);
  });

  it("member ve bilinmeyen roller yönetici değildir", () => {
    expect(isOrgManagerRole("member")).toBe(false);
    expect(isOrgManagerRole("")).toBe(false);
    expect(isOrgManagerRole("guest")).toBe(false);
  });
});
