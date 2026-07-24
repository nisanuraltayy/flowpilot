/**
 * Engellenen görev çözümleme çakışma sınıflandırması — GERÇEK backend mesajlarıyla;
 * ham detay ekrana taşınmaz (blocked_task_handlers.py str(exc) mesajları birebir).
 */

import { describe, expect, it } from "vitest";

import {
  CANDIDATE_INACTIVE_MESSAGE,
  classifyBlockedTaskConflict,
  GENERIC_CONFLICT_MESSAGE,
  NO_ASSIGNMENT_MESSAGE,
  NOT_BLOCKED_MESSAGE,
} from "@/features/blocked-tasks/conflict";

describe("classifyBlockedTaskConflict", () => {
  it("task blocked değil → not_blocked", () => {
    expect(classifyBlockedTaskConflict("task self-approval nedeniyle blocked değil")).toEqual({
      kind: "not_blocked",
      message: NOT_BLOCKED_MESSAGE,
    });
  });

  it("aktif rol ataması yok → no_assignment", () => {
    expect(
      classifyBlockedTaskConflict("finance için aktif rol ataması yok — önce atama yapılmalı"),
    ).toEqual({ kind: "no_assignment", message: NO_ASSIGNMENT_MESSAGE });
  });

  it("aday aktif üye değil → candidate_inactive", () => {
    expect(classifyBlockedTaskConflict("aday aktif üye değil — atanamaz")).toEqual({
      kind: "candidate_inactive",
      message: CANDIDATE_INACTIVE_MESSAGE,
    });
  });

  it("çözümleme çakışması / bilinmeyen → güvenli genel; ham detay sızmaz", () => {
    const r = classifyBlockedTaskConflict("çözümleme çakışması SECRET-INTERNAL");
    expect(r.kind).toBe("conflict");
    expect(r.message).toBe(GENERIC_CONFLICT_MESSAGE);
    expect(r.message).not.toContain("SECRET-INTERNAL");
  });
});
