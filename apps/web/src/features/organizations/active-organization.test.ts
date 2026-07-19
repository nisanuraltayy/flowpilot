/**
 * Aktif organizasyon SAF karar mantığı testleri (0/1/çok org, geçerli/stale cookie).
 * Cookie authorization DEĞİLDİR: stale cookie yok sayılır.
 */

import { describe, expect, it } from "vitest";

import {
  activeOrgCookieOptions,
  decideActiveOrganization,
} from "@/features/organizations/active-organization";
import type { MyOrganization } from "@/lib/api/resources";

function org(id: string, name = "Org"): MyOrganization {
  return { organizationId: id, name, membershipKind: "owner", membershipStatus: "active" };
}

describe("decideActiveOrganization", () => {
  it("hiç org yoksa 'none' (onboarding)", () => {
    expect(decideActiveOrganization([], null).kind).toBe("none");
    expect(decideActiveOrganization([], "some-uuid").kind).toBe("none");
  });

  it("tek org + cookie yok → 'auto' (otomatik seç)", () => {
    const decision = decideActiveOrganization([org("a")], null);
    expect(decision.kind).toBe("auto");
    if (decision.kind === "auto") {
      expect(decision.organization.organizationId).toBe("a");
    }
  });

  it("çok org + cookie yok → 'select'", () => {
    const decision = decideActiveOrganization([org("a"), org("b")], null);
    expect(decision.kind).toBe("select");
    if (decision.kind === "select") {
      expect(decision.organizations).toHaveLength(2);
    }
  });

  it("cookie geçerli aktif üyeliğe işaret ediyorsa → 'active'", () => {
    const decision = decideActiveOrganization([org("a"), org("b")], "b");
    expect(decision.kind).toBe("active");
    if (decision.kind === "active") {
      expect(decision.organization.organizationId).toBe("b");
    }
  });

  it("stale cookie (artık üye değil) YOK SAYILIR → çok org ise 'select'", () => {
    const decision = decideActiveOrganization([org("a"), org("b")], "zzz-not-a-member");
    expect(decision.kind).toBe("select");
  });

  it("stale cookie + tek org → 'auto' (o tek org)", () => {
    const decision = decideActiveOrganization([org("a")], "stale");
    expect(decision.kind).toBe("auto");
  });
});

describe("activeOrgCookieOptions", () => {
  it("HttpOnly + SameSite=Lax + Path=/ her zaman; Secure yalnız production", () => {
    expect(activeOrgCookieOptions(false)).toEqual({
      httpOnly: true,
      sameSite: "lax",
      secure: false,
      path: "/",
    });
    expect(activeOrgCookieOptions(true).secure).toBe(true);
  });
});
