/** Davet görüntüleme yardımcıları — saf eşleme + güvenli fallback testleri. */

import { describe, expect, it } from "vitest";

import {
  invitationRoleLabel,
  invitationStatusLabel,
  invitationStatusTone,
  isInvitationRevocable,
} from "@/features/invitations/display";

describe("invitationStatusLabel", () => {
  it("bilinen durumları Türkçe etiketler", () => {
    expect(invitationStatusLabel("pending")).toBe("Bekliyor");
    expect(invitationStatusLabel("accepted")).toBe("Kabul edildi");
    expect(invitationStatusLabel("revoked")).toBe("İptal edildi");
    expect(invitationStatusLabel("expired")).toBe("Süresi doldu");
  });

  it("bilinmeyen durumda uydurma yapmaz, ham değeri döner", () => {
    expect(invitationStatusLabel("weird_state")).toBe("weird_state");
  });
});

describe("invitationStatusTone", () => {
  it("durumu rozet tonuna eşler; bilinmeyen → neutral", () => {
    expect(invitationStatusTone("pending")).toBe("pending");
    expect(invitationStatusTone("accepted")).toBe("success");
    expect(invitationStatusTone("expired")).toBe("error");
    expect(invitationStatusTone("???")).toBe("neutral");
  });
});

describe("invitationRoleLabel", () => {
  it("admin/member → Türkçe; owner sunulmaz ama fallback güvenli", () => {
    expect(invitationRoleLabel("admin")).toBe("Yönetici");
    expect(invitationRoleLabel("member")).toBe("Üye");
    expect(invitationRoleLabel("owner")).toBe("owner");
  });
});

describe("isInvitationRevocable", () => {
  it("yalnız pending iptal edilebilir", () => {
    expect(isInvitationRevocable("pending")).toBe(true);
    for (const s of ["accepted", "revoked", "expired"]) {
      expect(isInvitationRevocable(s)).toBe(false);
    }
  });
});
