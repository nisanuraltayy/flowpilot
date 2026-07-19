import { describe, expect, it } from "vitest";

import { membershipKindLabel } from "@/features/organizations/labels";

describe("membershipKindLabel", () => {
  it("bilinen üyelik türlerini Türkçeye çevirir", () => {
    expect(membershipKindLabel("owner")).toBe("Sahip");
    expect(membershipKindLabel("member")).toBe("Üye");
    expect(membershipKindLabel("admin")).toBe("Yönetici");
  });

  it("bilinmeyen türü ham döner", () => {
    expect(membershipKindLabel("guest")).toBe("guest");
  });
});
