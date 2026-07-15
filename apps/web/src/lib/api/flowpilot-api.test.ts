/**
 * FastAPI istemcisi testleri — mock fetch, network YOK.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createOrganization } from "@/lib/api/flowpilot-api";

const TEST_TOKEN = "test-access-token-marker";

function mockFetchOnce(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createOrganization", () => {
  it("Bearer header'ı server-side ekler ve 201'i doğrular", async () => {
    const fetchMock = mockFetchOnce(201, {
      organization_id: "11111111-1111-4111-8111-111111111111",
      owner_membership_id: "22222222-2222-4222-8222-222222222222",
      name: "Acme",
    });

    const outcome = await createOrganization(TEST_TOKEN, "Acme");

    expect(outcome.kind).toBe("created");
    if (outcome.kind === "created") {
      expect(outcome.organization.organizationId).toBe(
        "11111111-1111-4111-8111-111111111111",
      );
      expect(outcome.organization.name).toBe("Acme");
    }

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/organizations");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      `Bearer ${TEST_TOKEN}`,
    );
    expect(init.cache).toBe("no-store");
  });

  it("bozuk 201 gövdesini reddeder (kör güven yok)", async () => {
    mockFetchOnce(201, { organization_id: "not-a-uuid", name: "" });

    const outcome = await createOrganization(TEST_TOKEN, "Acme");

    expect(outcome.kind).toBe("server_error");
  });

  it("401'i unauthorized'a eşler", async () => {
    mockFetchOnce(401, { detail: "Access token gecersiz." });
    expect((await createOrganization(TEST_TOKEN, "Acme")).kind).toBe("unauthorized");
  });

  it("422'de backend'in kullanıcı-dostu detail mesajını taşır", async () => {
    mockFetchOnce(422, { detail: "Organizasyon adi bos olamaz." });

    const outcome = await createOrganization(TEST_TOKEN, "   ");

    expect(outcome.kind).toBe("validation_error");
    if (outcome.kind === "validation_error") {
      expect(outcome.message).toBe("Organizasyon adi bos olamaz.");
    }
  });

  it("422'de teknik dizi detail'i kullanıcıya TAŞIMAZ (generic mesaj)", async () => {
    mockFetchOnce(422, {
      detail: [{ loc: ["body", "name"], msg: "field required", type: "missing" }],
    });

    const outcome = await createOrganization(TEST_TOKEN, "x");

    expect(outcome.kind).toBe("validation_error");
    if (outcome.kind === "validation_error") {
      expect(outcome.message).not.toContain("field required");
    }
  });

  it("503'ü service_unavailable'a eşler", async () => {
    mockFetchOnce(503, { detail: "unavailable" });
    expect((await createOrganization(TEST_TOKEN, "Acme")).kind).toBe(
      "service_unavailable",
    );
  });

  it("500'ü server_error'a eşler", async () => {
    mockFetchOnce(500, "Internal Server Error");
    expect((await createOrganization(TEST_TOKEN, "Acme")).kind).toBe("server_error");
  });

  it("timeout/network hatasını network_error'a eşler ve token sızdırmaz", async () => {
    const fn = vi
      .fn()
      .mockRejectedValue(new DOMException("The operation timed out.", "TimeoutError"));
    vi.stubGlobal("fetch", fn);

    const outcome = await createOrganization(TEST_TOKEN, "Acme");

    expect(outcome.kind).toBe("network_error");
    // Sonuç nesnesinin hiçbir yerinde token bulunmaz.
    expect(JSON.stringify(outcome)).not.toContain(TEST_TOKEN);
  });
});
