/**
 * Route koruma yardımcıları — proxy'nin saf karar fonksiyonları.
 */

import { describe, expect, it } from "vitest";

import { isAuthPage, isProtectedPath } from "@/lib/supabase/proxy";

describe("isProtectedPath", () => {
  it("onboarding ve dashboard korumalıdır", () => {
    expect(isProtectedPath("/onboarding")).toBe(true);
    expect(isProtectedPath("/onboarding/organization")).toBe(true);
    expect(isProtectedPath("/dashboard")).toBe(true);
  });

  it("organizasyon seçimi, talepler ve görev kutusu korumalıdır", () => {
    expect(isProtectedPath("/organizations/select")).toBe(true);
    expect(isProtectedPath("/purchase-requests")).toBe(true);
    expect(isProtectedPath("/purchase-requests/new")).toBe(true);
    expect(isProtectedPath("/tasks/inbox")).toBe(true);
  });

  it("login, signup, auth ve kök korumalı değildir", () => {
    expect(isProtectedPath("/login")).toBe(false);
    expect(isProtectedPath("/signup")).toBe(false);
    expect(isProtectedPath("/auth/check-email")).toBe(false);
    expect(isProtectedPath("/auth/error")).toBe(false);
    expect(isProtectedPath("/")).toBe(false);
  });

  it("benzer önekli ama farklı yolları korumalı saymaz", () => {
    expect(isProtectedPath("/dashboard-public")).toBe(false);
    expect(isProtectedPath("/onboardingx")).toBe(false);
  });
});

describe("isAuthPage", () => {
  it("login ve signup auth sayfalarıdır", () => {
    expect(isAuthPage("/login")).toBe(true);
    expect(isAuthPage("/signup")).toBe(true);
    expect(isAuthPage("/dashboard")).toBe(false);
  });
});
