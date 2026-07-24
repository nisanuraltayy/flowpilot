/** Onay rolü yönetimi görünürlüğü + aday uygunluğu (SAF). */

import { describe, expect, it } from "vitest";

import {
  canManageApprovalRoles,
  eligibleApprovalCandidates,
} from "@/features/approval-roles/permissions";
import type { MemberListItem } from "@/lib/api/resources";

function member(o: Partial<MemberListItem>): MemberListItem {
  return {
    membershipId: `mem-${o.userId ?? "1"}`,
    userId: o.userId ?? "u1",
    email: "email" in o ? (o.email as string | null) : "a@b.com",
    role: o.role ?? "member",
    status: o.status ?? "active",
    version: 1,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  };
}

describe("canManageApprovalRoles", () => {
  it("owner/admin yönetebilir; member ve bilinmeyen yönetemez", () => {
    expect(canManageApprovalRoles("owner")).toBe(true);
    expect(canManageApprovalRoles("admin")).toBe(true);
    expect(canManageApprovalRoles("member")).toBe(false);
    expect(canManageApprovalRoles("guest")).toBe(false);
  });
});

describe("eligibleApprovalCandidates", () => {
  it("yalnız aktif üyeleri aday yapar (suspended/removed elenir)", () => {
    const members = [
      member({ userId: "a", status: "active" }),
      member({ userId: "b", status: "suspended" }),
      member({ userId: "c", status: "removed" }),
      member({ userId: "d", status: "active" }),
    ];
    const ids = eligibleApprovalCandidates(members).map((m) => m.userId);
    expect(ids).toEqual(["a", "d"]);
  });

  it("aktif üye yoksa boş aday listesi", () => {
    const members = [member({ userId: "b", status: "suspended" })];
    expect(eligibleApprovalCandidates(members)).toEqual([]);
  });
});
