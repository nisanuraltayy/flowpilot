import { describe, expect, it } from "vitest";

import { signInSchema, signUpSchema } from "@/features/auth/schemas";

describe("signInSchema", () => {
  it("geçerli e-posta ve şifreyi kabul eder", () => {
    const result = signInSchema.safeParse({ email: "a@b.com", password: "x" });
    expect(result.success).toBe(true);
  });

  it("geçersiz e-postayı reddeder", () => {
    const result = signInSchema.safeParse({ email: "not-an-email", password: "x" });
    expect(result.success).toBe(false);
  });

  it("boş şifreyi reddeder", () => {
    const result = signInSchema.safeParse({ email: "a@b.com", password: "" });
    expect(result.success).toBe(false);
  });
});

describe("signUpSchema", () => {
  it("kısa şifreyi reddeder", () => {
    const result = signUpSchema.safeParse({
      email: "a@b.com",
      password: "kisa",
      passwordConfirm: "kisa",
    });
    expect(result.success).toBe(false);
  });

  it("şifre tekrarı uyuşmazlığını reddeder", () => {
    const result = signUpSchema.safeParse({
      email: "a@b.com",
      password: "yeterince-uzun",
      passwordConfirm: "farkli-sifre-123",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path[0] === "passwordConfirm")).toBe(true);
    }
  });

  it("eşleşen geçerli şifreleri kabul eder", () => {
    const result = signUpSchema.safeParse({
      email: "a@b.com",
      password: "yeterince-uzun",
      passwordConfirm: "yeterince-uzun",
    });
    expect(result.success).toBe(true);
  });
});
