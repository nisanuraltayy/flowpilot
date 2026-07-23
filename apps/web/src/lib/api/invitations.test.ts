/**
 * Davet kaynak istemcisi testleri — mock fetch, GERÇEK network YOK.
 *
 * Doğrulanan: create/accept Idempotency-Key header'ı, preview PUBLIC (Authorization YOK),
 * 403/410 → forbidden/gone, ham token sonuçlarda SIZMAZ, snake→camel eşleme.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  acceptInvitation,
  createInvitation,
  listInvitations,
  previewInvitation,
  revokeInvitation,
} from "@/lib/api/resources";

const TOKEN = "secret-access-token-marker";
const RAW_TOKEN = "raw-invitation-token-marker";
const ORG = "11111111-1111-4111-8111-111111111111";
const INV = "22222222-2222-4222-8222-222222222222";
const MEMBERSHIP = "33333333-3333-4333-8333-333333333333";

function mockFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

function lastInit(fn: ReturnType<typeof vi.fn>): RequestInit {
  return fn.mock.calls[0][1] as RequestInit;
}

function lastUrl(fn: ReturnType<typeof vi.fn>): string {
  return fn.mock.calls[0][0] as string;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listInvitations", () => {
  it("Bearer ekler, doğru URL, gövdeyi eşler", async () => {
    const fn = mockFetch(200, {
      items: [
        {
          invitation_id: INV,
          invited_email: "a@b.com",
          role: "member",
          status: "pending",
          expires_at: "2026-07-30T00:00:00Z",
          created_at: "2026-07-23T00:00:00Z",
        },
      ],
    });
    const outcome = await listInvitations(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].invitedEmail).toBe("a@b.com");
      expect(outcome.data[0].status).toBe("pending");
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/invitations`);
    expect((lastInit(fn).headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("403 → forbidden (member)", async () => {
    mockFetch(403, { detail: "yetki yok" });
    expect((await listInvitations(TOKEN, ORG)).kind).toBe("forbidden");
  });
});

describe("createInvitation", () => {
  it("Idempotency-Key + body gönderir, token/acceptUrl eşler", async () => {
    const fn = mockFetch(201, {
      invitation_id: INV,
      invited_email: "a@b.com",
      role: "admin",
      status: "pending",
      expires_at: "2026-07-30T00:00:00Z",
      accept_url: "http://x/invitations/accept?org=1&token=2",
      token: RAW_TOKEN,
      duplicate: false,
    });
    const outcome = await createInvitation(TOKEN, ORG, {
      email: "a@b.com",
      role: "admin",
      idempotencyKey: "idem-key-1",
    });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.token).toBe(RAW_TOKEN);
      expect(outcome.data.duplicate).toBe(false);
    }
    const headers = lastInit(fn).headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("idem-key-1");
    expect(JSON.parse(String(lastInit(fn).body))).toMatchObject({ email: "a@b.com", role: "admin" });
  });

  it("idempotent replay: token null, duplicate true", async () => {
    mockFetch(201, {
      invitation_id: INV,
      invited_email: "a@b.com",
      role: "member",
      status: "pending",
      expires_at: "2026-07-30T00:00:00Z",
      accept_url: null,
      token: null,
      duplicate: true,
    });
    const outcome = await createInvitation(TOKEN, ORG, {
      email: "a@b.com",
      role: "member",
      idempotencyKey: "k",
    });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.token).toBeNull();
      expect(outcome.data.duplicate).toBe(true);
    }
  });

  it("422 backend mesajını taşır, 409 çakışmayı döner", async () => {
    mockFetch(422, { detail: "Geçersiz e-posta." });
    const v = await createInvitation(TOKEN, ORG, { email: "x", role: "member", idempotencyKey: "k" });
    expect(v.kind).toBe("validation_error");
    mockFetch(409, { detail: "Zaten davet var." });
    const c = await createInvitation(TOKEN, ORG, { email: "a@b.com", role: "member", idempotencyKey: "k" });
    expect(c.kind).toBe("conflict");
  });
});

describe("revokeInvitation", () => {
  it("doğru URL, duplicate bayrağını eşler", async () => {
    const fn = mockFetch(200, { invitation_id: INV, status: "revoked", duplicate: true });
    const outcome = await revokeInvitation(TOKEN, ORG, INV);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.status).toBe("revoked");
      expect(outcome.data.duplicate).toBe(true);
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/invitations/${INV}/revoke`);
  });
});

describe("previewInvitation (PUBLIC)", () => {
  it("Authorization header GÖNDERMEZ; org+token query, gövdeyi eşler", async () => {
    const fn = mockFetch(200, {
      organization_id: ORG,
      organization_name: "Acme",
      role: "member",
      expires_at: "2026-07-30T00:00:00Z",
      status: "pending",
    });
    const outcome = await previewInvitation(ORG, RAW_TOKEN);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.organizationName).toBe("Acme");
      expect(outcome.data.status).toBe("pending");
    }
    const headers = (lastInit(fn).headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(lastUrl(fn)).toContain("/v1/invitations/preview?");
    expect(lastUrl(fn)).toContain(`org=${ORG}`);
  });

  it("410 → gone (süresi dolmuş), 404 → not_found", async () => {
    mockFetch(410, { detail: "Davet suresi dolmus." });
    expect((await previewInvitation(ORG, RAW_TOKEN)).kind).toBe("gone");
    mockFetch(404, { detail: "Kaynak bulunamadi." });
    expect((await previewInvitation(ORG, RAW_TOKEN)).kind).toBe("not_found");
  });
});

describe("acceptInvitation", () => {
  it("Idempotency-Key + body, membership eşler, token sızmaz", async () => {
    const fn = mockFetch(200, {
      organization_id: ORG,
      membership_id: MEMBERSHIP,
      role: "member",
      status: "active",
      duplicate: false,
    });
    const outcome = await acceptInvitation(TOKEN, {
      organizationId: ORG,
      token: RAW_TOKEN,
      idempotencyKey: "accept-key-1",
    });
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.membershipId).toBe(MEMBERSHIP);
      expect(outcome.data.status).toBe("active");
    }
    const headers = lastInit(fn).headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("accept-key-1");
    expect(JSON.parse(String(lastInit(fn).body))).toMatchObject({
      organization_id: ORG,
      token: RAW_TOKEN,
    });
    expect(JSON.stringify(outcome)).not.toContain(RAW_TOKEN);
  });

  it("403 → forbidden (e-posta uyuşmazlığı), 410 → gone, 404 → not_found, 409 → conflict", async () => {
    mockFetch(403, { detail: "Davet e-postasi eslesmiyor." });
    expect((await acceptInvitation(TOKEN, { organizationId: ORG, token: RAW_TOKEN, idempotencyKey: "k" })).kind).toBe("forbidden");
    mockFetch(410, { detail: "Davet suresi dolmus." });
    expect((await acceptInvitation(TOKEN, { organizationId: ORG, token: RAW_TOKEN, idempotencyKey: "k" })).kind).toBe("gone");
    mockFetch(404, { detail: "Kaynak bulunamadi." });
    expect((await acceptInvitation(TOKEN, { organizationId: ORG, token: RAW_TOKEN, idempotencyKey: "k" })).kind).toBe("not_found");
    mockFetch(409, { detail: "Islem tamamlanamadi." });
    expect((await acceptInvitation(TOKEN, { organizationId: ORG, token: RAW_TOKEN, idempotencyKey: "k" })).kind).toBe("conflict");
  });
});
