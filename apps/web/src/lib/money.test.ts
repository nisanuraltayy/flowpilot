/**
 * Para parsing/formatting testleri — float ÜRETİLMEDİĞİ kritik olarak doğrulanır.
 */

import { describe, expect, it } from "vitest";

import { formatMinorAsTry, parseTryToMinor } from "@/lib/money";

describe("parseTryToMinor", () => {
  it("tam sayı TL'yi kuruşa çevirir", () => {
    expect(parseTryToMinor("12500")).toEqual({ ok: true, amountMinor: 1_250_000 });
  });

  it("virgüllü kuruşu doğru çevirir", () => {
    expect(parseTryToMinor("12500,50")).toEqual({ ok: true, amountMinor: 1_250_050 });
  });

  it("binlik ayıracı (nokta) + ondalık (virgül) biçimini destekler", () => {
    expect(parseTryToMinor("12.500,50")).toEqual({ ok: true, amountMinor: 1_250_050 });
    expect(parseTryToMinor("12.500")).toEqual({ ok: true, amountMinor: 1_250_000 });
  });

  it("tek haneli kuruşu 2 haneye tamamlar", () => {
    expect(parseTryToMinor("1,5")).toEqual({ ok: true, amountMinor: 150 });
  });

  it("baştaki/sondaki boşlukları yok sayar", () => {
    expect(parseTryToMinor("  1.250,00  ")).toEqual({ ok: true, amountMinor: 125_000 });
  });

  it("boş değeri reddeder", () => {
    expect(parseTryToMinor("")).toEqual({ ok: false, reason: "empty" });
    expect(parseTryToMinor("   ")).toEqual({ ok: false, reason: "empty" });
  });

  it("sıfır ve negatifi reddeder", () => {
    expect(parseTryToMinor("0")).toEqual({ ok: false, reason: "non_positive" });
    expect(parseTryToMinor("0,00")).toEqual({ ok: false, reason: "non_positive" });
    expect(parseTryToMinor("-5")).toEqual({ ok: false, reason: "non_positive" });
  });

  it("harf/geçersiz biçimi reddeder", () => {
    expect(parseTryToMinor("12abc").ok).toBe(false);
    expect(parseTryToMinor("12,505").ok).toBe(false); // 3 haneli kuruş
    expect(parseTryToMinor("1,2,3").ok).toBe(false);
    expect(parseTryToMinor("12.50.0,5").ok).toBe(true); // noktalar binlik sayılır → 12500,50
  });

  it("float ARİTMETİĞİ kullanmaz (0.1+0.2 tuzağı)", () => {
    // 0,1 + 0,2 float'ta 0.30000000000000004; kuruş tam sayısında tam 30 olmalı.
    expect(parseTryToMinor("0,30")).toEqual({ ok: true, amountMinor: 30 });
    // Büyük değer güvenli integer kalır.
    const big = parseTryToMinor("99999999,99");
    expect(big).toEqual({ ok: true, amountMinor: 9_999_999_999 });
  });
});

describe("formatMinorAsTry", () => {
  it("kuruşu TL biçimine çevirir", () => {
    expect(formatMinorAsTry(1_250_050)).toBe("12.500,50 ₺");
    expect(formatMinorAsTry(1_250_000)).toBe("12.500,00 ₺");
    expect(formatMinorAsTry(5)).toBe("0,05 ₺");
  });
});
