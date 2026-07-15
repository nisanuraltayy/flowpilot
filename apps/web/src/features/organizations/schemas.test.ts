import { describe, expect, it } from "vitest";

import {
  ORGANIZATION_NAME_MAX_LENGTH,
  organizationNameSchema,
} from "@/features/organizations/schemas";

describe("organizationNameSchema", () => {
  it("geçerli adı kabul eder ve kırpar", () => {
    const result = organizationNameSchema.safeParse({ name: "  Acme  " });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBe("Acme");
    }
  });

  it("boş adı reddeder", () => {
    expect(organizationNameSchema.safeParse({ name: "" }).success).toBe(false);
  });

  it("yalnızca boşluk içeren adı reddeder", () => {
    expect(organizationNameSchema.safeParse({ name: "   \t " }).success).toBe(false);
  });

  it("üst sınırı aşan adı reddeder", () => {
    const tooLong = "a".repeat(ORGANIZATION_NAME_MAX_LENGTH + 1);
    expect(organizationNameSchema.safeParse({ name: tooLong }).success).toBe(false);
  });

  it("tam sınırdaki adı kabul eder", () => {
    const atLimit = "a".repeat(ORGANIZATION_NAME_MAX_LENGTH);
    expect(organizationNameSchema.safeParse({ name: atLimit }).success).toBe(true);
  });
});
