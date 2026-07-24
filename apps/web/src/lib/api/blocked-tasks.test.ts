/**
 * Engellenen görev kaynak istemcisi testleri — mock fetch, GERÇEK network YOK.
 *
 * Doğrulanan: list mapping (null pr/requester + blocked_reason), resolve POST (BODY YOK —
 * backend user_id/version almaz), resolve response mapping, 401/403/404/409/422, hassas alan yok.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  listBlockedApprovalTasks,
  resolveBlockedApprovalTaskAssignment,
} from "@/lib/api/resources";

const TOKEN = "secret-access-token-marker";
const ORG = "11111111-1111-4111-8111-111111111111";
const TASK = "22222222-2222-4222-8222-222222222222";
const PR = "33333333-3333-4333-8333-333333333333";
const REQ = "44444444-4444-4444-8444-444444444444";
const ASSIGNEE = "55555555-5555-4555-8555-555555555555";

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

describe("listBlockedApprovalTasks", () => {
  it("Bearer + URL; null pr/requester eşlenir; hassas alan sızmaz", async () => {
    const fn = mockFetch(200, {
      items: [
        {
          task_id: TASK,
          purchase_request_id: PR,
          approver_role: "finance",
          status: "blocked",
          blocked_reason: "self_approval_no_eligible_assignee",
          requester_user_id: REQ,
          version: 2,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-10T00:00:00Z",
        },
        {
          task_id: "66666666-6666-4666-8666-666666666666",
          purchase_request_id: null,
          approver_role: "team_manager",
          status: "blocked",
          blocked_reason: null,
          requester_user_id: null,
          version: 1,
          created_at: "2026-07-02T00:00:00Z",
          updated_at: "2026-07-11T00:00:00Z",
        },
      ],
    });
    const outcome = await listBlockedApprovalTasks(TOKEN, ORG);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data[0].blockedReason).toBe("self_approval_no_eligible_assignee");
      expect(outcome.data[0].requesterUserId).toBe(REQ);
      expect(outcome.data[1].purchaseRequestId).toBeNull();
      expect(outcome.data[1].requesterUserId).toBeNull();
      expect(JSON.stringify(outcome)).not.toContain("provider_subject");
      expect(JSON.stringify(outcome)).not.toContain("auth_provider");
    }
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/approval-tasks/blocked`);
    expect((lastInit(fn).headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("403 → forbidden, 404 → not_found", async () => {
    mockFetch(403, { detail: "yok" });
    expect((await listBlockedApprovalTasks(TOKEN, ORG)).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await listBlockedApprovalTasks(TOKEN, ORG)).kind).toBe("not_found");
  });
});

describe("resolveBlockedApprovalTaskAssignment", () => {
  it("POST /{task_id}/resolve-assignment; BODY göndermez (user_id/version yok)", async () => {
    const fn = mockFetch(200, {
      task_id: TASK,
      purchase_request_id: PR,
      approver_role: "finance",
      status: "active",
      assigned_user_id: ASSIGNEE,
      version: 3,
    });
    const outcome = await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK);
    expect(outcome.kind).toBe("ok");
    if (outcome.kind === "ok") {
      expect(outcome.data.assignedUserId).toBe(ASSIGNEE);
      expect(outcome.data.status).toBe("active");
      expect(outcome.data.version).toBe(3);
    }
    expect(lastInit(fn).method).toBe("POST");
    expect(lastUrl(fn)).toContain(`/v1/organizations/${ORG}/approval-tasks/${TASK}/resolve-assignment`);
    expect(lastInit(fn).body).toBeUndefined();
  });

  it("hata eşlemeleri: 401/403/404/409/422", async () => {
    mockFetch(401, {});
    expect((await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK)).kind).toBe("unauthorized");
    mockFetch(403, { detail: "yok" });
    expect((await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK)).kind).toBe("forbidden");
    mockFetch(404, { detail: "yok" });
    expect((await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK)).kind).toBe("not_found");
    mockFetch(409, { detail: "task self-approval nedeniyle blocked değil" });
    const c = await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK);
    expect(c.kind).toBe("conflict");
    if (c.kind === "conflict") expect(c.message).toContain("blocked değil");
    mockFetch(422, { detail: "geçersiz" });
    expect((await resolveBlockedApprovalTaskAssignment(TOKEN, ORG, TASK)).kind).toBe("validation_error");
  });
});
