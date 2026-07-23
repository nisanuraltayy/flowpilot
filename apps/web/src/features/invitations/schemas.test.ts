/** Davet oluşturma şeması — istemci-yakın doğrulama (nihai kaynak backend). */

import { describe, expect, it } from "vitest";

import { createInvitationSchema } from "@/features/invitations/schemas";

describe("createInvitationSchema", () => {
  it("geçerli e-posta + rol kabul eder ve e-postayı trim'ler", () => {
    const parsed = createInvitationSchema.safeParse({ email: "  a@b.com  ", role: "member" });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.email).toBe("a@b.com");
      expect(parsed.data.role).toBe("member");
    }
  });

  it("boş/geçersiz e-postayı reddeder", () => {
    expect(createInvitationSchema.safeParse({ email: "", role: "admin" }).success).toBe(false);
    expect(createInvitationSchema.safeParse({ email: "gecersiz", role: "admin" }).success).toBe(false);
  });

  it("admin/member dışındaki rolü reddeder (owner sunulmaz)", () => {
    expect(createInvitationSchema.safeParse({ email: "a@b.com", role: "owner" }).success).toBe(false);
    expect(createInvitationSchema.safeParse({ email: "a@b.com", role: "admin" }).success).toBe(true);
  });
});
