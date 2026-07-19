/**
 * FlowPilot kaynak istemcisi testleri — mock fetch, GERÇEK network YOK.
 *
 * Doğrulanan: Bearer server-side eklenir, aktif organizasyon doğru URL'de kullanılır,
 * Zod bozuk gövdeyi reddeder, HTTP durum kodları güvenli sonuçlara eşlenir,
 * Idempotency-Key header'ı gönderilir ve token hiçbir sonuçta sızmaz.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createPurchaseRequest,
  decideApprovalTask,
  getMyTaskInbox,
  getPurchaseRequest,
  getPurchaseRequestTimeline,
  listMyOrganizations,
  listMyPurchaseRequests,
} from "@/lib/api/resources";

const TOKEN = "secret-access-token-marker";
const ORG = "11111111-1111-4111-8111-111111111111";
const PR = "22222222-2222-4222-8222-222222222222";
const TASK = "33333333-3333-4333-8333-333333333333";

function mockFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue(
    new Response(status === 204 ? null : JSON.stringify(body), {
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

describe("listMyOrganizations", () => {
  it("Bearer ekler, doğru URL'i kullanır ve gövdeyi eşler", async () => {
    const fn = mockFetch(200, {
      items: [
        { organization_id: ORG, name: "Acme", membership_kind: "owner", membership_status: "active" },
      ],
    });

    const outcome = await listMyOrganizations(TOKEN);

    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].organizationId).toBe(ORG);
      expect(outcome.data[0].membershipKind).toBe("owner");
    }
    expect(lastUrl(fn)).toContain("/v1/me/organizations");
    expect((lastInit(fn).headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(lastInit(fn).cache).toBe("no-store");
  });

  it("bozuk gövdeyi reddeder (server_error)", async () => {
    mockFetch(200, { items: [{ organization_id: "not-a-uuid" }] });
    expect((await listMyOrganizations(TOKEN)).kind).toBe("server_error");
  });

  it("401 → unauthorized ve token sonuca sızmaz", async () => {
    mockFetch(401, { detail: "gecersiz" });
    const outcome = await listMyOrganizations(TOKEN);
    expect(outcome.kind).toBe("unauthorized");
    expect(JSON.stringify(outcome)).not.toContain(TOKEN);
  });
});

describe("createPurchaseRequest", () => {
  it("aktif organizasyonu URL'de kullanır ve 201'i eşler", async () => {
    const fn = mockFetch(201, {
      purchase_request_id: PR,
      organization_id: ORG,
      workflow_instance_id: "44444444-4444-4444-8444-444444444444",
      status: "in_approval",
      title: "Talep",
      amount_minor: 1_250_000,
      currency: "TRY",
      current_approval_role: "team_manager",
      created_at: "2026-07-19T00:00:00Z",
    });

    const outcome = await createPurchaseRequest(TOKEN, ORG, {
      title: "Talep",
      description: null,
      amountMinor: 1_250_000,
      currency: "TRY",
    });

    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.amountMinor).toBe(1_250_000);
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/purchase-requests`);
    const body = JSON.parse(String(lastInit(fn).body));
    expect(body).toMatchObject({ amount_minor: 1_250_000, currency: "TRY" });
  });

  it("422'de backend'in kullanıcı-dostu mesajını taşır", async () => {
    mockFetch(422, { detail: "Tutar 0'dan büyük olmalı." });
    const outcome = await createPurchaseRequest(TOKEN, ORG, {
      title: "x",
      description: null,
      amountMinor: 0,
      currency: "TRY",
    });
    expect(outcome.kind).toBe("validation_error");
    if (outcome.kind === "validation_error") {
      expect(outcome.message).toBe("Tutar 0'dan büyük olmalı.");
    }
  });

  it("422'de teknik dizi detail'i kullanıcıya TAŞIMAZ", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "amount_minor"], msg: "int required" }] });
    const outcome = await createPurchaseRequest(TOKEN, ORG, {
      title: "x",
      description: null,
      amountMinor: 1,
      currency: "TRY",
    });
    expect(outcome.kind).toBe("validation_error");
    if (outcome.kind === "validation_error") {
      expect(outcome.message).not.toContain("int required");
    }
  });
});

describe("listMyPurchaseRequests / getPurchaseRequest / timeline / inbox", () => {
  it("liste gövdesini eşler", async () => {
    mockFetch(200, {
      items: [
        {
          purchase_request_id: PR,
          title: "T",
          amount_minor: 500,
          currency: "TRY",
          status: "approved",
          current_approval_role: null,
          created_at: "2026-07-19T00:00:00Z",
          updated_at: "2026-07-19T00:00:00Z",
        },
      ],
    });
    const outcome = await listMyPurchaseRequests(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].status).toBe("approved");
    }
  });

  it("detay 404 → not_found", async () => {
    mockFetch(404, { detail: "Kaynak bulunamadi." });
    expect((await getPurchaseRequest(TOKEN, ORG, PR)).kind).toBe("not_found");
  });

  it("timeline gövdesini eşler", async () => {
    const fn = mockFetch(200, {
      purchase_request_id: PR,
      items: [
        {
          event_type: "purchase_request.created",
          occurred_at: "2026-07-19T00:00:00Z",
          actor_is_current_user: true,
          role_key: null,
          task_id: null,
          message: "Talep oluşturuldu.",
        },
      ],
    });
    const outcome = await getPurchaseRequestTimeline(TOKEN, ORG, PR);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].eventType).toBe("purchase_request.created");
    }
    expect(lastUrl(fn)).toContain(`/purchase-requests/${PR}/timeline`);
  });

  it("inbox gövdesini eşler", async () => {
    mockFetch(200, {
      items: [
        {
          task_id: TASK,
          purchase_request_id: PR,
          purchase_request_title: "T",
          amount_minor: 500,
          currency: "TRY",
          required_role: "finance",
          status: "active",
          workflow_instance_id: "55555555-5555-4555-8555-555555555555",
          created_at: "2026-07-19T00:00:00Z",
          due_at: null,
        },
      ],
    });
    const outcome = await getMyTaskInbox(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].requiredRole).toBe("finance");
    }
  });
});

describe("decideApprovalTask", () => {
  it("Idempotency-Key header'ı gönderir ve duplicate bayrağını eşler", async () => {
    const fn = mockFetch(200, {
      task_id: TASK,
      decision: "approved",
      purchase_request_id: PR,
      purchase_request_status: "approved",
      workflow_status: "completed",
      next_approval_role: null,
      decided_at: "2026-07-19T00:00:00Z",
      duplicate: true,
    });

    const outcome = await decideApprovalTask(TOKEN, ORG, TASK, {
      decision: "approve",
      comment: null,
      idempotencyKey: "idem-key-123",
    });

    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.duplicate).toBe(true);
    }
    const headers = lastInit(fn).headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("idem-key-123");
    expect(lastUrl(fn)).toContain(`/tasks/${TASK}/decision`);
  });

  it("409 çakışmayı güvenli mesajla döner", async () => {
    mockFetch(409, { detail: "Karar çakışması." });
    const outcome = await decideApprovalTask(TOKEN, ORG, TASK, {
      decision: "approve",
      comment: null,
      idempotencyKey: "k",
    });
    expect(outcome.kind).toBe("conflict");
    if (outcome.kind === "conflict") {
      expect(outcome.message).toBe("Karar çakışması.");
    }
  });

  it("503 → service_unavailable", async () => {
    mockFetch(503, { detail: "x" });
    expect(
      (await decideApprovalTask(TOKEN, ORG, TASK, { decision: "reject", comment: null, idempotencyKey: "k" }))
        .kind,
    ).toBe("service_unavailable");
  });

  it("timeout/network → network_error, token sızmaz", async () => {
    const fn = vi.fn().mockRejectedValue(new DOMException("timed out", "TimeoutError"));
    vi.stubGlobal("fetch", fn);
    const outcome = await decideApprovalTask(TOKEN, ORG, TASK, {
      decision: "approve",
      comment: null,
      idempotencyKey: "k",
    });
    expect(outcome.kind).toBe("network_error");
    expect(JSON.stringify(outcome)).not.toContain(TOKEN);
  });
});
