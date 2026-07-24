/**
 * Next.js baseline security header sözleşmesi (FP-OPS-003B).
 *
 * next.config.ts saf bir config nesnesidir; import'u Next.js runtime veya
 * environment side effect'i OLUŞTURMAZ. Bu test yalnız config sözleşmesini
 * pinler: beş temel header, catch-all kapsam, duplicate yokluğu ve bu dilimde
 * BİLİNÇLİ olarak eklenmeyen header'ların yokluğu.
 */

import { describe, expect, it } from "vitest";

import nextConfig from "../next.config";

interface HeaderEntry {
  readonly key: string;
  readonly value: string;
}

interface HeaderRoute {
  readonly source: string;
  readonly headers: readonly HeaderEntry[];
}

async function resolveHeaderRoutes(): Promise<readonly HeaderRoute[]> {
  expect(typeof nextConfig.headers).toBe("function");
  const routes = (await nextConfig.headers?.()) ?? [];
  return routes as readonly HeaderRoute[];
}

const EXPECTED_HEADERS: Record<string, string> = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

const FORBIDDEN_HEADERS = [
  "content-security-policy",
  "content-security-policy-report-only",
  "strict-transport-security",
  "access-control-allow-origin",
  "cross-origin-embedder-policy",
  "cache-control",
];

describe("next.config security headers (FP-OPS-003B)", () => {
  it("headers() tek catch-all route config'i döndürür", async () => {
    const routes = await resolveHeaderRoutes();

    expect(routes).toHaveLength(1);
    expect(routes[0]?.source).toBe("/(.*)");
  });

  it("beş temel header tam değerleriyle mevcut", async () => {
    const [route] = await resolveHeaderRoutes();
    const actual = new Map(route!.headers.map((h) => [h.key, h.value]));

    for (const [key, value] of Object.entries(EXPECTED_HEADERS)) {
      expect(actual.get(key), key).toBe(value);
    }
    expect(route!.headers).toHaveLength(Object.keys(EXPECTED_HEADERS).length);
  });

  it("header adları case-insensitive olarak unique", async () => {
    const [route] = await resolveHeaderRoutes();
    const names = route!.headers.map((h) => h.key.toLowerCase());

    expect(new Set(names).size).toBe(names.length);
  });

  it("next.config headers() CSP eklemiyor — CSP YALNIZ proxy katmanından gelir (FP-OPS-004A); HSTS/CORS/COEP/Cache-Control da yok", async () => {
    const [route] = await resolveHeaderRoutes();
    const names = new Set(route!.headers.map((h) => h.key.toLowerCase()));

    for (const forbidden of FORBIDDEN_HEADERS) {
      expect(names.has(forbidden), forbidden).toBe(false);
    }
  });

  it("unsafe-inline/unsafe-eval hiçbir değerde geçmiyor", async () => {
    const [route] = await resolveHeaderRoutes();
    const allValues = route!.headers.map((h) => h.value).join(" ");

    expect(allValues).not.toContain("unsafe-inline");
    expect(allValues).not.toContain("unsafe-eval");
  });

  it("standalone output korunuyor", () => {
    expect(nextConfig.output).toBe("standalone");
  });

  it("config import'u environment side effect'i oluşturmuyor", () => {
    // Saf nesne: fonksiyon dışında yalnız veri alanları bulunur; poweredByHeader
    // gibi alanlara DOKUNULMAMIŞTIR (bu dilimde değiştirilmesi yasak).
    expect(nextConfig.poweredByHeader).toBeUndefined();
    expect(Object.keys(nextConfig).sort()).toEqual(["headers", "output"]);
  });
});
