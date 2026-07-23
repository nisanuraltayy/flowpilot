/** Üye yönetimi görünürlük kuralları — owner/admin/self/removed matrisi (SAF). */

import { describe, expect, it } from "vitest";

import { memberRowPermissions, type MemberTarget } from "@/features/members/permissions";

const target = (o: Partial<MemberTarget> = {}): MemberTarget => ({
  email: "target@x.com",
  role: "member",
  status: "active",
  ...o,
});

describe("memberRowPermissions — owner actor", () => {
  const owner = (t: MemberTarget) => memberRowPermissions("owner", "me@x.com", t);

  it("aktif member: owner+admin rol seçenekleri, suspend/remove açık, reactivate kapalı", () => {
    const p = owner(target({ role: "member", status: "active" }));
    expect(p.manageable).toBe(true);
    expect([...p.roleOptions].sort()).toEqual(["admin", "owner"]);
    expect(p.canSuspend).toBe(true);
    expect(p.canReactivate).toBe(false);
    expect(p.canRemove).toBe(true);
  });

  it("başka bir owner: admin+member seçenekleri (düşürme; son-owner backend'de)", () => {
    const p = owner(target({ role: "owner", status: "active" }));
    expect([...p.roleOptions].sort()).toEqual(["admin", "member"]);
  });

  it("askıya alınmış admin: reactivate açık, suspend kapalı, remove açık", () => {
    const p = owner(target({ role: "admin", status: "suspended" }));
    expect(p.canReactivate).toBe(true);
    expect(p.canSuspend).toBe(false);
    expect(p.canRemove).toBe(true);
  });

  it("removed hedef: hiçbir aksiyon (terminal)", () => {
    const p = owner(target({ status: "removed" }));
    expect(p.manageable).toBe(false);
    expect(p.reason).toBe("removed");
    expect(p.roleOptions).toEqual([]);
    expect(p.canRemove).toBe(false);
  });
});

describe("memberRowPermissions — admin actor", () => {
  const admin = (t: MemberTarget) => memberRowPermissions("admin", "me@x.com", t);

  it("aktif member: yalnız admin rol seçeneği (owner YOK), suspend/remove açık", () => {
    const p = admin(target({ role: "member", status: "active" }));
    expect(p.manageable).toBe(true);
    expect(p.roleOptions).toEqual(["admin"]);
    expect(p.roleOptions).not.toContain("owner");
    expect(p.canSuspend).toBe(true);
    expect(p.canRemove).toBe(true);
  });

  it("admin hedefi yönetemez (not_permitted)", () => {
    const p = admin(target({ role: "admin", status: "active" }));
    expect(p.manageable).toBe(false);
    expect(p.reason).toBe("not_permitted");
  });

  it("owner hedefi yönetemez (not_permitted)", () => {
    const p = admin(target({ role: "owner", status: "active" }));
    expect(p.manageable).toBe(false);
    expect(p.reason).toBe("not_permitted");
  });

  it("askıya alınmış member: reactivate + remove açık, rol admin", () => {
    const p = admin(target({ role: "member", status: "suspended" }));
    expect(p.canReactivate).toBe(true);
    expect(p.canRemove).toBe(true);
    expect(p.roleOptions).toEqual(["admin"]);
  });
});

describe("memberRowPermissions — self", () => {
  it("self satır (büyük/küçük harf duyarsız): hiçbir aksiyon", () => {
    const p = memberRowPermissions("owner", "Me@X.com", target({ email: "me@x.COM", role: "owner" }));
    expect(p.isSelf).toBe(true);
    expect(p.manageable).toBe(false);
    expect(p.reason).toBe("self");
  });

  it("null email → self değil", () => {
    const p = memberRowPermissions("owner", null, target({ email: null }));
    expect(p.isSelf).toBe(false);
  });
});
