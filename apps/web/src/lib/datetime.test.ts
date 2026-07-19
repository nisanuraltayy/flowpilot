import { describe, expect, it } from "vitest";

import { formatDateTime } from "@/lib/datetime";

describe("formatDateTime", () => {
  it("geçerli ISO zaman damgasını okunaklı metne çevirir", () => {
    const output = formatDateTime("2026-07-19T09:30:00Z");
    // Yerel biçim; en azından yıl ve ayrık bir metin üretmeli (ham ISO değil).
    expect(output).not.toBe("2026-07-19T09:30:00Z");
    expect(output).toContain("2026");
  });

  it("geçersiz girdiyi güvenli biçimde ham döner", () => {
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
  });
});
