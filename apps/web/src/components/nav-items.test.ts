/** Navigasyon görünürlüğü — Davetler yalnız owner/admin'e gösterilir (UX-only). */

import { describe, expect, it } from "vitest";

import { NAV_ITEMS, visibleNavItems } from "@/components/nav-items";

describe("visibleNavItems", () => {
  it("yönetici için Davetler dahil tüm öğeleri gösterir", () => {
    const keys = visibleNavItems(true).map((i) => i.key);
    expect(keys).toContain("invitations");
    expect(visibleNavItems(true)).toHaveLength(NAV_ITEMS.length);
  });

  it("member için Davetler gizlenir; temel öğeler kalır", () => {
    const items = visibleNavItems(false);
    const keys = items.map((i) => i.key);
    expect(keys).not.toContain("invitations");
    expect(keys).toEqual(["overview", "new", "requests", "inbox"]);
  });

  it("Davetler öğesi requiresManage ile işaretlidir ve doğru yola gider", () => {
    const invitations = NAV_ITEMS.find((i) => i.key === "invitations");
    expect(invitations?.requiresManage).toBe(true);
    expect(invitations?.href).toBe("/settings/team/invitations");
  });
});
