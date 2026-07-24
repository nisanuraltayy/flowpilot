/**
 * Production environment fail-fast testleri (FP-OPS-001).
 *
 * - Production RUNTIME'da eksik değişken localhost'a SESSİZCE düşmez.
 * - Build fazında (`next build`) kontrol UYGULANMAZ — CI secret'sız build alabilmelidir.
 * - Development/test davranışı BOZULMAZ (güvenli local default).
 * - Hata mesajları değişken ADI içerir, DEĞER içermez.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl, getAppUrl, getSupabaseConfig } from "@/lib/env";

const KEYS = [
  "NODE_ENV",
  "NEXT_PHASE",
  "FLOWPILOT_API_BASE_URL",
  "NEXT_PUBLIC_APP_URL",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
] as const;

let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));
});

afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k];
    else vi.stubEnv(k, v);
  }
  vi.unstubAllEnvs();
});

function setEnv(values: Partial<Record<(typeof KEYS)[number], string | undefined>>) {
  for (const [k, v] of Object.entries(values)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
}

describe("getApiBaseUrl", () => {
  it("development'ta güvenli local default döner", () => {
    setEnv({ NODE_ENV: "development", FLOWPILOT_API_BASE_URL: undefined });
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("production RUNTIME'da eksikse localhost'a düşmez, hata verir", () => {
    setEnv({ NODE_ENV: "production", NEXT_PHASE: undefined, FLOWPILOT_API_BASE_URL: undefined });
    expect(() => getApiBaseUrl()).toThrowError(/FLOWPILOT_API_BASE_URL/);
    expect(() => getApiBaseUrl()).not.toThrowError(/127\.0\.0\.1/);
  });

  it("production BUILD fazında kontrol uygulanmaz (secret'sız build)", () => {
    setEnv({
      NODE_ENV: "production",
      NEXT_PHASE: "phase-production-build",
      FLOWPILOT_API_BASE_URL: undefined,
    });
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("production'da tanımlıysa verilen değeri döner", () => {
    setEnv({ NODE_ENV: "production", FLOWPILOT_API_BASE_URL: "http://api.internal:8000" });
    expect(getApiBaseUrl()).toBe("http://api.internal:8000");
  });
});

describe("getAppUrl", () => {
  it("development'ta güvenli local default döner", () => {
    setEnv({ NODE_ENV: "development", NEXT_PUBLIC_APP_URL: undefined });
    expect(getAppUrl()).toBe("http://localhost:3000");
  });

  it("production RUNTIME'da eksikse hata verir", () => {
    setEnv({ NODE_ENV: "production", NEXT_PHASE: undefined, NEXT_PUBLIC_APP_URL: undefined });
    expect(() => getAppUrl()).toThrowError(/NEXT_PUBLIC_APP_URL/);
  });

  it("production'da tanımlıysa verilen değeri döner", () => {
    setEnv({ NODE_ENV: "production", NEXT_PUBLIC_APP_URL: "https://app.example.com" });
    expect(getAppUrl()).toBe("https://app.example.com");
  });
});

describe("getSupabaseConfig", () => {
  it("development'ta eksikse null döner (kontrollü degrade)", () => {
    setEnv({
      NODE_ENV: "development",
      NEXT_PUBLIC_SUPABASE_URL: undefined,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: undefined,
    });
    expect(getSupabaseConfig()).toBeNull();
  });

  it("production RUNTIME'da eksikse fail-fast eder ve rebuild gerektiğini söyler", () => {
    setEnv({
      NODE_ENV: "production",
      NEXT_PHASE: undefined,
      NEXT_PUBLIC_SUPABASE_URL: undefined,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: undefined,
    });
    expect(() => getSupabaseConfig()).toThrowError(/NEXT_PUBLIC_SUPABASE_URL/);
    expect(() => getSupabaseConfig()).toThrowError(/yeniden derleyin/i);
  });

  it("production BUILD fazında null döner (build patlamaz)", () => {
    setEnv({
      NODE_ENV: "production",
      NEXT_PHASE: "phase-production-build",
      NEXT_PUBLIC_SUPABASE_URL: undefined,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: undefined,
    });
    expect(getSupabaseConfig()).toBeNull();
  });

  it("tanımlıysa yapılandırmayı döner", () => {
    setEnv({
      NODE_ENV: "production",
      NEXT_PUBLIC_SUPABASE_URL: "https://p.supabase.co",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "publishable-key",
    });
    expect(getSupabaseConfig()).toEqual({
      url: "https://p.supabase.co",
      publishableKey: "publishable-key",
    });
  });
});
