/**
 * Onay rolü kaynak istemcisi testleri — mock fetch, GERÇEK network YOK.
 *
 * Doğrulanan: list mapping (null email dahil), PUT body (ilk atamada expected_version YOK;
 * değiştirmede VAR), duplicate, 401/403/404/409/422 eşlemeleri, hassas alanların sızmaması.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { assignApprovalRole, listApprovalRoleAssignments } from "@/lib/api/resources";

const TOKEN = "secret-access-token-marker";
const ORG = "11111111-1111-4111-8111-111111111111";
const U1 = "22222222-2222-4222-8222-222222222222";
const ASG = "33333333-3333-4333-8333-333333333333";

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

describe("listApprovalRoleAssignments", () => {
  it("Bearer + URL; null email eşlenir; hassas alan sızmaz", async () => {
    const fn = mockFetch(200, {
      items: [
        {
          assignment_id: ASG,
          role_key: "team_manager",
          assigned_user_id: U1,
          assigned_user_email: "a@b.com",
          status: "active",
          version: 2,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-10T00:00:00Z",
        },
        {
          assignment_id: "44444444-4444-4444-8444-444444444444",
          role_key: "finance",
          assigned_user_id: "55555555-5555-4555-8555-555555555555",
          assigned_user_email: null,
          status: "active",
          version: 1,
          created_at: "2026-07-02T00:00:00Z",
          updated_at: "2026-07-11T00:00:00Z",
        },
      ],
    });
    const outcome = await listApprovalRoleAssignments(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].roleKey).toBe("team_manager");
      expect(outcome.data[0].assignedUserEmail).toBe("a@b.com");
      expect(outcome.data[1].assignedUserEmail).toBeNull();
      expect(JSON.stringify(outcome)).not.toContain("provider_subject");
      expect(JSON.stringify(outcome)).not.toContain("auth_provider");
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/approval-roles`);
    expect((lastInit(fn).headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("403 → forbidden, 404 → not_found", async () => {
    mockFetch(403, { detail: "yok" });
    expect((await listApprovalRoleAssignments(TOKEN, ORG)).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await listApprovalRoleAssignments(TOKEN, ORG)).kind).toBe("not_found");
  });
});

describe("assignApprovalRole", () => {
  it("ilk atama: PUT /{role_key}, body { user_id } (expected_version YOK)", async () => {
    const fn = mockFetch(200, {
      assignment_id: ASG,
      role_key: "finance",
      assigned_user_id: U1,
      assigned_user_email: "a@b.com",
      status: "active",
      version: 1,
      duplicate: false,
    });
    const outcome = await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1 });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.roleKey).toBe("finance");
      expect(outcome.data.version).toBe(1);
    }
    expect(lastInit(fn).method).toBe("PUT");
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/approval-roles/finance`);
    const body = JSON.parse(String(lastInit(fn).body));
    expect(body).toEqual({ user_id: U1 });
    expect(body.expected_version).toBeUndefined();
  });

  it("değiştirme: expected_version body'ye eklenir", async () => {
    const fn = mockFetch(200, {
      assignment_id: ASG,
      role_key: "finance",
      assigned_user_id: U1,
      assigned_user_email: "a@b.com",
      status: "active",
      version: 3,
      duplicate: false,
    });
    await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1, expectedVersion: 2 });
    const body = JSON.parse(String(lastInit(fn).body));
    expect(body).toEqual({ user_id: U1, expected_version: 2 });
  });

  it("no-op → duplicate=true güvenle taşınır", async () => {
    mockFetch(200, {
      assignment_id: ASG,
      role_key: "finance",
      assigned_user_id: U1,
      assigned_user_email: "a@b.com",
      status: "active",
      version: 2,
      duplicate: true,
    });
    const outcome = await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1, expectedVersion: 2 });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.duplicate).toBe(true);
    }
  });

  it("hata eşlemeleri: 401/403/404/409/422", async () => {
    mockFetch(401, {});
    expect((await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1 })).kind).toBe("unauthorized");
    mockFetch(403, { detail: "yok" });
    expect((await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1 })).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1 })).kind).toBe("not_found");
    mockFetch(409, { detail: "stale expected_version" });
    const c = await assignApprovalRole(TOKEN, ORG, "finance", { userId: U1, expectedVersion: 1 });
    expect(c.kind).toBe("conflict");
    if (c.kind === "conflict") expect(c.message).toContain("stale");
    mockFetch(422, { detail: "geçersiz role_key: 'x'" });
    expect((await assignApprovalRole(TOKEN, ORG, "x", { userId: U1 })).kind).toBe("validation_error");
  });
});
