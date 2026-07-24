/**
 * CSP builder ve nonce sözleşme testleri (FP-OPS-004A).
 */

import { describe, expect, it } from "vitest";

import { buildContentSecurityPolicy, generateNonce } from "@/lib/csp";

const NONCE = generateNonce();

function directives(policy: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const part of policy.split("; ")) {
    const [name, ...values] = part.split(" ");
    expect(map.has(name!), `duplicate directive: ${name}`).toBe(false);
    map.set(name!, values.join(" "));
  }
  return map;
}

describe("generateNonce", () => {
  it("boş olmayan string döner", () => {
    const nonce = generateNonce();
    expect(typeof nonce).toBe("string");
    expect(nonce.length).toBeGreaterThan(0);
  });

  it("her çağrıda farklı değer üretir", () => {
    const seen = new Set(Array.from({ length: 50 }, () => generateNonce()));
    expect(seen.size).toBe(50);
  });

  it("128 bit entropy taşır (16 byte → 24 karakter base64)", () => {
    expect(generateNonce()).toHaveLength(24);
  });

  it("yalnız base64 karakter seti içerir", () => {
    for (let i = 0; i < 20; i += 1) {
      expect(generateNonce()).toMatch(/^[A-Za-z0-9+/]+={0,2}$/);
    }
  });

  it("CR/LF veya header ayracı içermez", () => {
    for (let i = 0; i < 20; i += 1) {
      const nonce = generateNonce();
      expect(nonce).not.toMatch(/[\r\n;,]/);
    }
  });
});

describe("buildContentSecurityPolicy — production", () => {
  const policy = buildContentSecurityPolicy({ nonce: NONCE });

  it("deterministiktir (aynı girdi → aynı politika)", () => {
    expect(buildContentSecurityPolicy({ nonce: NONCE })).toBe(policy);
  });

  it("beklenen directive setini tam olarak içerir", () => {
    expect([...directives(policy).keys()]).toEqual([
      "default-src",
      "base-uri",
      "object-src",
      "frame-ancestors",
      "form-action",
      "script-src",
      "style-src",
      "img-src",
      "font-src",
      "connect-src",
      "worker-src",
      "frame-src",
    ]);
  });

  it("temel kilitler doğru: default/object/frame 'none', base/form 'self'", () => {
    const map = directives(policy);
    expect(map.get("default-src")).toBe("'none'");
    expect(map.get("object-src")).toBe("'none'");
    expect(map.get("frame-ancestors")).toBe("'none'"); // X-Frame-Options: DENY ile uyumlu
    expect(map.get("frame-src")).toBe("'none'");
    expect(map.get("worker-src")).toBe("'none'");
    expect(map.get("base-uri")).toBe("'self'");
    expect(map.get("form-action")).toBe("'self'");
    expect(map.get("connect-src")).toBe("'self'");
    expect(map.get("style-src")).toBe("'self'");
    expect(map.get("img-src")).toBe("'self'");
    expect(map.get("font-src")).toBe("'self'");
  });

  it("script-src nonce + strict-dynamic içerir", () => {
    expect(directives(policy).get("script-src")).toBe(
      `'self' 'nonce-${NONCE}' 'strict-dynamic'`,
    );
  });

  it("unsafe-eval, unsafe-inline, data:, blob:, ws(s): ve dış origin İÇERMEZ", () => {
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("data:");
    expect(policy).not.toContain("blob:");
    expect(policy).not.toContain("ws:");
    expect(policy).not.toContain("wss:");
    expect(policy).not.toContain("supabase");
    expect(policy).not.toContain("http://");
    expect(policy).not.toContain("https://");
  });

  it("tek satırdır ve header-safe'tir", () => {
    expect(policy).not.toMatch(/[\r\n]/);
  });

  it("upgrade-insecure-requests, manifest-src ve media-src eklenmemiştir", () => {
    expect(policy).not.toContain("upgrade-insecure-requests");
    expect(policy).not.toContain("manifest-src");
    expect(policy).not.toContain("media-src");
  });
});

describe("buildContentSecurityPolicy — development", () => {
  const policy = buildContentSecurityPolicy({ nonce: NONCE, development: true });
  const map = directives(policy);

  it("unsafe-eval YALNIZ script-src içindedir", () => {
    expect(map.get("script-src")).toContain("'unsafe-eval'");
    expect(map.get("style-src")).not.toContain("unsafe-eval");
    expect(map.get("connect-src")).not.toContain("unsafe-eval");
  });

  it("unsafe-inline YALNIZ style-src içindedir (script-src'de ASLA)", () => {
    expect(map.get("style-src")).toContain("'unsafe-inline'");
    expect(map.get("script-src")).not.toContain("unsafe-inline");
  });

  it("ws: YALNIZ connect-src içindedir; wss: hiç yoktur", () => {
    expect(map.get("connect-src")).toBe("'self' ws:");
    expect(policy).not.toContain("wss:");
    expect(map.get("script-src")).not.toContain("ws:");
  });

  it("nonce + strict-dynamic development'ta da korunur", () => {
    expect(map.get("script-src")).toContain(`'nonce-${NONCE}'`);
    expect(map.get("script-src")).toContain("'strict-dynamic'");
  });
});

describe("header injection koruması", () => {
  it.each([
    "abc\r\ninjected",
    "abc; script-src *",
    "abc'unsafe-inline",
    " ",
    "",
    "abc def",
  ])("geçersiz nonce reddedilir: %j", (bad) => {
    expect(() => buildContentSecurityPolicy({ nonce: bad })).toThrow();
  });

  it("hata mesajı nonce değerini sızdırmaz", () => {
    try {
      buildContentSecurityPolicy({ nonce: "gizli-deger\r\n" });
      expect.unreachable();
    } catch (error) {
      expect(String(error)).not.toContain("gizli-deger");
    }
  });
});
