/**
 * Üye kaynak istemcisi testleri — mock fetch, GERÇEK network YOK.
 *
 * Doğrulanan: list mapping (null email + removed dahil), PATCH body (yalnız role/status + daima
 * expected_version), hata eşlemeleri (401/403/404/409/422), hassas alanların sonuçlarda olmaması.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { listOrganizationMembers, updateOrganizationMember } from "@/lib/api/resources";

const TOKEN = "secret-access-token-marker";
const ORG = "11111111-1111-4111-8111-111111111111";
const U1 = "22222222-2222-4222-8222-222222222222";
const U2 = "33333333-3333-4333-8333-333333333333";
const MEM1 = "44444444-4444-4444-8444-444444444444";

function mockFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
const lastInit = (fn: ReturnType<typeof vi.fn>): RequestInit => fn.mock.calls[0][1] as RequestInit;
const lastUrl = (fn: ReturnType<typeof vi.fn>): string => fn.mock.calls[0][0] as string;

afterEach(() => vi.unstubAllGlobals());

describe("listOrganizationMembers", () => {
  it("Bearer + URL; null email ve removed üyeyi doğru eşler; hassas alan sızmaz", async () => {
    const fn = mockFetch(200, {
      items: [
        {
          membership_id: MEM1,
          user_id: U1,
          email: "a@b.com",
          role: "owner",
          status: "active",
          version: 2,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-10T00:00:00Z",
        },
        {
          membership_id: "55555555-5555-4555-8555-555555555555",
          user_id: U2,
          email: null,
          role: "member",
          status: "removed",
          version: 5,
          created_at: "2026-07-02T00:00:00Z",
          updated_at: "2026-07-12T00:00:00Z",
        },
      ],
    });
    const outcome = await listOrganizationMembers(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].email).toBe("a@b.com");
      expect(outcome.data[0].version).toBe(2);
      expect(outcome.data[1].email).toBeNull();
      expect(outcome.data[1].status).toBe("removed");
      // Hassas identity mapping'e alınmaz.
      expect(JSON.stringify(outcome)).not.toContain("provider_subject");
      expect(JSON.stringify(outcome)).not.toContain("auth_provider");
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/members`);
    expect((lastInit(fn).headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("403 → forbidden, 404 → not_found", async () => {
    mockFetch(403, { detail: "yok" });
    expect((await listOrganizationMembers(TOKEN, ORG)).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await listOrganizationMembers(TOKEN, ORG)).kind).toBe("not_found");
  });
});

describe("updateOrganizationMember", () => {
  it("rol güncelleme: PATCH body { role, expected_version } (status YOK)", async () => {
    const fn = mockFetch(200, {
      membership_id: MEM1,
      user_id: U1,
      role: "admin",
      status: "active",
      version: 3,
      duplicate: false,
    });
    const outcome = await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 2 });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.role).toBe("admin");
      expect(outcome.data.version).toBe(3);
      expect(outcome.data.duplicate).toBe(false);
    }
    expect(lastInit(fn).method).toBe("PATCH");
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/members/${U1}`);
    const body = JSON.parse(String(lastInit(fn).body));
    expect(body).toEqual({ role: "admin", expected_version: 2 });
    expect(body.status).toBeUndefined();
  });

  it("durum güncelleme: PATCH body { status, expected_version } (role YOK)", async () => {
    const fn = mockFetch(200, {
      membership_id: MEM1,
      user_id: U1,
      role: "member",
      status: "suspended",
      version: 4,
      duplicate: false,
    });
    await updateOrganizationMember(TOKEN, ORG, U1, { status: "suspended", expectedVersion: 3 });
    const body = JSON.parse(String(lastInit(fn).body));
    expect(body).toEqual({ status: "suspended", expected_version: 3 });
    expect(body.role).toBeUndefined();
  });

  it("no-op → duplicate=true güvenle taşınır", async () => {
    mockFetch(200, {
      membership_id: MEM1,
      user_id: U1,
      role: "admin",
      status: "active",
      version: 2,
      duplicate: true,
    });
    const outcome = await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 2 });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.duplicate).toBe(true);
    }
  });

  it("hata eşlemeleri: 401/403/404/409/422", async () => {
    mockFetch(401, {});
    expect((await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 1 })).kind).toBe("unauthorized");
    mockFetch(403, { detail: "yok" });
    expect((await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 1 })).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 1 })).kind).toBe("not_found");
    mockFetch(409, { detail: "stale expected_version" });
    const c = await updateOrganizationMember(TOKEN, ORG, U1, { role: "admin", expectedVersion: 1 });
    expect(c.kind).toBe("conflict");
    if (c.kind === "conflict") {
      expect(c.message).toContain("stale");
    }
    mockFetch(422, { detail: "geçersiz rol" });
    expect((await updateOrganizationMember(TOKEN, ORG, U1, { role: "x", expectedVersion: 1 })).kind).toBe("validation_error");
  });
});
