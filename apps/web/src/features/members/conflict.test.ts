/**
 * Üye 409 sınıflandırması — GERÇEK backend domain mesajlarıyla; ham detay ekrana taşınmaz.
 * (Backend str(exc) mesajları member_handlers.py / membership.py'den birebir alınmıştır.)
 */

import { describe, expect, it } from "vitest";

import {
  APPROVAL_RESP_MESSAGE,
  classifyMemberConflict,
  FINAL_OWNER_MESSAGE,
  GENERIC_CONFLICT_MESSAGE,
  INVALID_TRANSITION_MESSAGE,
  REMOVED_MESSAGE,
  SELF_MESSAGE,
  STALE_MESSAGE,
} from "@/features/members/conflict";

describe("classifyMemberConflict", () => {
  it("stale expected_version / eşzamanlı → stale", () => {
    expect(classifyMemberConflict("stale expected_version")).toEqual({
      kind: "stale",
      message: STALE_MESSAGE,
    });
    expect(classifyMemberConflict("üyelik eşzamanlı değişti (stale version)").kind).toBe("stale");
  });

  it("kendi üyeliği → self", () => {
    expect(classifyMemberConflict("kullanıcı kendi üyeliğini değiştiremez")).toEqual({
      kind: "self",
      message: SELF_MESSAGE,
    });
  });

  it("son aktif owner → final_owner", () => {
    expect(classifyMemberConflict("son aktif owner korunur")).toEqual({
      kind: "final_owner",
      message: FINAL_OWNER_MESSAGE,
    });
  });

  it("onay sorumlulukları → approval_responsibility", () => {
    expect(
      classifyMemberConflict("önce kullanıcının aktif onay sorumlulukları yeniden atanmalıdır"),
    ).toEqual({ kind: "approval_responsibility", message: APPROVAL_RESP_MESSAGE });
  });

  it("kaldırılmış üyelik → removed", () => {
    expect(classifyMemberConflict("kaldırılmış üyelik değiştirilemez")).toEqual({
      kind: "removed",
      message: REMOVED_MESSAGE,
    });
  });

  it("geçersiz status geçişi → invalid_transition", () => {
    expect(classifyMemberConflict("geçersiz status geçişi: active → removed")).toEqual({
      kind: "invalid_transition",
      message: INVALID_TRANSITION_MESSAGE,
    });
  });

  it("bilinmeyen 409 → güvenli genel çakışma", () => {
    const r = classifyMemberConflict("beklenmeyen içsel durum xyz");
    expect(r.kind).toBe("conflict");
    expect(r.message).toBe(GENERIC_CONFLICT_MESSAGE);
  });

  it("mesaj daima güvenli sabittir; ham backend detay'ı SIZMAZ", () => {
    const raw = "son aktif owner korunur INTERNAL-DETAIL-XYZ";
    const r = classifyMemberConflict(raw);
    expect(r.message).toBe(FINAL_OWNER_MESSAGE);
    expect(r.message).not.toContain("INTERNAL-DETAIL-XYZ");
  });
});
