/** Navigasyon görünürlüğü — Davetler yalnız owner/admin'e gösterilir (UX-only). */

import { describe, expect, it } from "vitest";

import { NAV_ITEMS, visibleNavItems } from "@/components/nav-items";

describe("visibleNavItems", () => {
  it("yönetici için Davetler dahil tüm öğeleri gösterir", () => {
    const keys = visibleNavItems(true).map((i) => i.key);
    expect(keys).toContain("invitations");
    expect(visibleNavItems(true)).toHaveLength(NAV_ITEMS.length);
  });

  it("member için yönetim öğeleri (Üyeler/Davetler) gizlenir; temel öğeler kalır", () => {
    const items = visibleNavItems(false);
    const keys = items.map((i) => i.key);
    expect(keys).not.toContain("invitations");
    expect(keys).not.toContain("members");
    expect(keys).toEqual(["overview", "new", "requests", "inbox"]);
  });

  it("yönetici için Üyeler bağlantısı görünür ve doğru yola gider", () => {
    const keys = visibleNavItems(true).map((i) => i.key);
    expect(keys).toContain("members");
    const members = NAV_ITEMS.find((i) => i.key === "members");
    expect(members?.requiresManage).toBe(true);
    expect(members?.href).toBe("/settings/team/members");
  });

  it("Davetler öğesi requiresManage ile işaretlidir ve doğru yola gider", () => {
    const invitations = NAV_ITEMS.find((i) => i.key === "invitations");
    expect(invitations?.requiresManage).toBe(true);
    expect(invitations?.href).toBe("/settings/team/invitations");
  });
});
