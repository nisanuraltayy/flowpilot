import { describe, expect, it } from "vitest";

import { sanitizeInternalPath } from "@/lib/redirect";

const FALLBACK = "/onboarding/organization";

describe("sanitizeInternalPath — open redirect koruması", () => {
  it("uygulama içi yolu aynen kabul eder", () => {
    expect(sanitizeInternalPath("/dashboard")).toBe("/dashboard");
  });

  it("dış URL'yi varsayılana düşürür", () => {
    expect(sanitizeInternalPath("https://evil.example/phish")).toBe(FALLBACK);
  });

  it("protokol-göreli URL'yi (//host) reddeder", () => {
    expect(sanitizeInternalPath("//evil.example")).toBe(FALLBACK);
  });

  it("backslash hilesini (/\\host) reddeder", () => {
    expect(sanitizeInternalPath("/\\evil.example")).toBe(FALLBACK);
  });

  it("null/boş değerde varsayılana düşer", () => {
    expect(sanitizeInternalPath(null)).toBe(FALLBACK);
    expect(sanitizeInternalPath("")).toBe(FALLBACK);
  });
});
