/**
 * 404 nonce-uyum sözleşmesi (FP-OPS-004C).
 *
 * Doğrulanmış hata: `_not-found` build'de prerender edildiğinde HTML'i
 * nonce'suz framework script'leri içerir ve enforce edilen CSP 404
 * hydration'ını bloklar (Chrome console kanıtı, FP-OPS-004B).
 *
 * Çözüm sözleşmesi: custom not-found component'i `connection()` bekleyerek
 * request-time render'a geçer. Bu test, sözleşmenin kaynak düzeyinde
 * korunmasını pinler (satır silinirse 404-CSP regresyonu sessizce geri döner;
 * prerender-manifest doğrulaması build gerektirdiğinden runtime katmanında
 * ayrıca yapılır — bkz. FP-OPS-004B doğrulama prosedürü).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(join(__dirname, "not-found.tsx"), "utf-8");

describe("not-found CSP sözleşmesi", () => {
  it("connection() ile request-time render'a geçer (prerender edilmez)", () => {
    expect(SOURCE).toContain('import { connection } from "next/server"');
    expect(SOURCE).toContain("await connection()");
  });

  it("async server component'tir ve client API kullanmaz", () => {
    expect(SOURCE).toContain("export default async function NotFound");
    expect(SOURCE).not.toContain('"use client"');
    expect(SOURCE).not.toContain("useEffect");
    expect(SOURCE).not.toContain("useState");
  });

  it("UX sözleşmesi korunur: 404 içeriği ve panel bağlantısı durur", () => {
    expect(SOURCE).toContain("404");
    expect(SOURCE).toContain("Sayfa bulunamadı");
    expect(SOURCE).toContain('href="/dashboard"');
  });
});
