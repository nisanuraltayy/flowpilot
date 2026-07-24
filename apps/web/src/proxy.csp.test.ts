/**
 * Proxy CSP entegrasyon sözleşmesi (FP-OPS-004A).
 *
 * Supabase yapılandırılmadan (test ortamı) proxy'nin gerçek davranışı test
 * edilir: `updateSession` config'siz dalda çalışır — session ağı GEREKMEZ.
 * Davranış sözleşmesi test edilir, implementation detail'e kilitlenilmez.
 */

import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import proxy, { config } from "@/proxy";

const CSP = "content-security-policy";

function request(path: string): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`);
}

describe("proxy CSP davranışı", () => {
  it("response'a CSP header'ı tam olarak BİR kez yazar", async () => {
    const response = await proxy(request("/login"));
    const value = response.headers.get(CSP);

    expect(value).toBeTruthy();
    // Headers.get duplicate'leri virgülle birleştirir; ikinci bir politika
    // ", default-src" olarak görünürdü.
    expect(value).not.toContain(", default-src");
  });

  it("request header'ına AYNI politikayı yazar (render katmanı nonce'ı buradan okur)", async () => {
    const req = request("/login");
    const response = await proxy(req);

    expect(req.headers.get(CSP)).toBe(response.headers.get(CSP));
  });

  it("her request farklı nonce alır", async () => {
    const first = (await proxy(request("/login"))).headers.get(CSP)!;
    const second = (await proxy(request("/login"))).headers.get(CSP)!;

    const nonce = (policy: string) => policy.match(/'nonce-([^']+)'/)?.[1];
    expect(nonce(first)).toBeTruthy();
    expect(nonce(second)).toBeTruthy();
    expect(nonce(first)).not.toBe(nonce(second));
  });

  it("test ortamında strict (production-benzeri) politika uygulanır", async () => {
    const policy = (await proxy(request("/login"))).headers.get(CSP)!;

    expect(policy).toContain("default-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("ws:");
  });

  it("Report-Only header'ı ASLA yazılmaz", async () => {
    const response = await proxy(request("/login"));

    expect(response.headers.get("content-security-policy-report-only")).toBeNull();
  });

  it("nonce cookie'ye veya başka bir custom header'a yazılmaz", async () => {
    const response = await proxy(request("/login"));
    const nonce = response.headers.get(CSP)!.match(/'nonce-([^']+)'/)![1]!;

    expect(response.headers.get("x-nonce")).toBeNull();
    for (const cookie of response.headers.getSetCookie()) {
      expect(cookie).not.toContain(nonce);
    }
  });

  it("korumalı yol redirect'i korunur ve redirect yanıtı da CSP taşır", async () => {
    // Supabase yapılandırılmamış test ortamında korumalı yol login'e yönlenir.
    const response = await proxy(request("/dashboard"));

    expect(response.status).toBeGreaterThanOrEqual(300);
    expect(response.status).toBeLessThan(400);
    expect(response.headers.get("location")).toContain("/login");
    expect(response.headers.get(CSP)).toBeTruthy();
  });

  it("login/signup davranışı değişmez (redirect üretmez, normal akış)", async () => {
    for (const path of ["/login", "/signup"]) {
      const response = await proxy(request(path));
      expect(response.headers.get("location")).toBeNull();
    }
  });
});

describe("matcher kapsamı sözleşmesi", () => {
  const pattern = config.matcher[0]!;

  it("static asset'ler, Next iç yolları ve auth/callback hariçtir", () => {
    expect(pattern).toContain("_next/static");
    expect(pattern).toContain("_next/image");
    expect(pattern).toContain("favicon.ico");
    expect(pattern).toContain("auth/callback");
  });

  it("Supabase session mantığı ile CSP aynı matcher'ı paylaşır (tek matcher)", () => {
    expect(config.matcher).toHaveLength(1);
  });
});
