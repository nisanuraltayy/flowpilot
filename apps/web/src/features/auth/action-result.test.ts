import { describe, expect, it } from "vitest";

import {
  errorResult,
  IDLE_RESULT,
  SUPABASE_NOT_CONFIGURED_MESSAGE,
} from "@/features/auth/action-result";

describe("action-result", () => {
  it("IDLE_RESULT idle durumundadır", () => {
    expect(IDLE_RESULT).toEqual({ status: "idle" });
  });

  it("errorResult mesajı taşır", () => {
    const result = errorResult("hata oldu");
    expect(result).toEqual({ status: "error", message: "hata oldu", fieldErrors: undefined });
  });

  it("errorResult alan hatalarını taşır", () => {
    const result = errorResult("kontrol edin", { email: ["geçersiz"] });
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.fieldErrors?.email).toEqual(["geçersiz"]);
    }
  });

  it("yapılandırılmamış mesajı service role/secret içermez", () => {
    expect(SUPABASE_NOT_CONFIGURED_MESSAGE).not.toMatch(/service.?role|secret/i);
  });
});
