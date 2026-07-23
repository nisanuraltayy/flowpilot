/** Üye görüntüleme yardımcıları — saf eşleme + güvenli fallback. */

import { describe, expect, it } from "vitest";

import {
  memberEmailLabel,
  memberRoleLabel,
  memberStatusLabel,
  memberStatusTone,
} from "@/features/members/display";

describe("memberRoleLabel", () => {
  it("owner/admin/member → Türkçe; bilinmeyen ham kalır", () => {
    expect(memberRoleLabel("owner")).toBe("Sahip");
    expect(memberRoleLabel("admin")).toBe("Yönetici");
    expect(memberRoleLabel("member")).toBe("Üye");
    expect(memberRoleLabel("weird")).toBe("weird");
  });
});

describe("memberStatusLabel / tone", () => {
  it("bilinen durumları etiketler ve tonlar", () => {
    expect(memberStatusLabel("active")).toBe("Aktif");
    expect(memberStatusLabel("suspended")).toBe("Askıya alındı");
    expect(memberStatusLabel("removed")).toBe("Kaldırıldı");
    expect(memberStatusTone("active")).toBe("success");
    expect(memberStatusTone("suspended")).toBe("pending");
    expect(memberStatusTone("removed")).toBe("neutral");
  });

  it("tarihsel invited güvenli fallback ile desteklenir", () => {
    expect(memberStatusLabel("invited")).toBe("Davet edildi");
  });

  it("bilinmeyen durum ham kalır, tonu neutral", () => {
    expect(memberStatusLabel("???")).toBe("???");
    expect(memberStatusTone("???")).toBe("neutral");
  });
});

describe("memberEmailLabel", () => {
  it("null/boş e-posta güvenli yer tutucu gösterir", () => {
    expect(memberEmailLabel(null)).toBe("E-posta bilgisi yok");
    expect(memberEmailLabel("")).toBe("E-posta bilgisi yok");
    expect(memberEmailLabel("a@b.com")).toBe("a@b.com");
  });
});
