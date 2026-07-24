/**
 * Onay rolü çakışma sınıflandırması — GERÇEK backend mesajlarıyla; ham detay ekrana taşınmaz.
 * (role_assignment_handlers.py / repository str(exc) mesajları birebir alınmıştır.)
 */

import { describe, expect, it } from "vitest";

import {
  classifyApprovalRoleConflict,
  GENERIC_CONFLICT_MESSAGE,
  INVALID_MEMBER_STATUS_MESSAGE,
  INVALID_ROLE_MESSAGE,
  STALE_MESSAGE,
} from "@/features/approval-roles/conflict";

describe("classifyApprovalRoleConflict", () => {
  it("stale / eşzamanlı / expected_version → stale", () => {
    expect(classifyApprovalRoleConflict("stale expected_version")).toEqual({
      kind: "stale",
      message: STALE_MESSAGE,
    });
    expect(classifyApprovalRoleConflict("atama eşzamanlı değişti (stale version)").kind).toBe("stale");
    expect(classifyApprovalRoleConflict("aktif atama zaten var (eşzamanlı atama)").kind).toBe("stale");
    // 422 expected_version-required de refresh gerektirir → stale.
    expect(classifyApprovalRoleConflict("mevcut atama var; expected_version gerekli").kind).toBe("stale");
  });

  it("hedef üyelik aktif değil → invalid_member_status", () => {
    expect(classifyApprovalRoleConflict("hedef üyelik aktif değil — atanamaz")).toEqual({
      kind: "invalid_member_status",
      message: INVALID_MEMBER_STATUS_MESSAGE,
    });
  });

  it("geçersiz role_key → invalid_role", () => {
    expect(classifyApprovalRoleConflict("geçersiz role_key: 'x'")).toEqual({
      kind: "invalid_role",
      message: INVALID_ROLE_MESSAGE,
    });
  });

  it("bilinmeyen → güvenli genel çakışma; ham detay sızmaz", () => {
    const r = classifyApprovalRoleConflict("beklenmeyen içsel durum SECRET-DETAIL");
    expect(r.kind).toBe("conflict");
    expect(r.message).toBe(GENERIC_CONFLICT_MESSAGE);
    expect(r.message).not.toContain("SECRET-DETAIL");
  });
});
