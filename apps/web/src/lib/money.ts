/**
 * Para yardımcıları — MVP'de yalnız TRY (Türk Lirası).
 *
 * Kurallar (FF-09 ile hizalı):
 * - Tutar MINOR UNIT (kuruş, integer) olarak taşınır; float ile hesaplanmaz.
 * - Kullanıcı TL biçiminde girer (örn. "12500,50" ya da "12.500,50").
 * - Parsing float ÜRETMEZ: string üzerinden tam sayı kuruş hesaplanır.
 * - Backend nihai doğrulama kaynağıdır; buradaki kontrol yalnız erken UX içindir.
 */

export const CURRENCY_TRY = "TRY";

export type MoneyParseResult =
  | { readonly ok: true; readonly amountMinor: number }
  | { readonly ok: false; readonly reason: "empty" | "format" | "non_positive" };

const MAX_MINOR = 9_999_999_999_999; // makul üst sınır (DoS/taşma koruması, ~100 milyar TL)

/**
 * TL biçimli bir metni kuruş (minor unit) tam sayısına çevirir. Float KULLANMAZ.
 *
 * Kabul: "12500", "12500,50", "12.500,50", "12.500", " 1.250,5 ".
 * Ret: boş, negatif, sıfır, harf/geçersiz format, 2 basamaktan fazla kuruş.
 */
export function parseTryToMinor(raw: string): MoneyParseResult {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, reason: "empty" };
  }
  if (trimmed.startsWith("-")) {
    return { ok: false, reason: "non_positive" };
  }

  // Binlik ayıracı olarak nokta, ondalık ayıracı olarak virgül (TR biçimi).
  // Yalnız rakam, nokta ve tek virgül kabul edilir.
  if (!/^[0-9.]+(,[0-9]{1,2})?$/.test(trimmed)) {
    return { ok: false, reason: "format" };
  }

  const [integerPart, fractionPart = ""] = trimmed.split(",");
  const digitsOnly = integerPart.replace(/\./g, "");
  if (digitsOnly === "" || !/^[0-9]+$/.test(digitsOnly)) {
    return { ok: false, reason: "format" };
  }

  const kurus = fractionPart.padEnd(2, "0"); // "5" -> "50", "" -> "00"
  // Tam sayı aritmetiği: (lira * 100) + kuruş — float yok.
  const lira = Number.parseInt(digitsOnly, 10);
  const fraction = Number.parseInt(kurus, 10);
  if (!Number.isSafeInteger(lira) || !Number.isSafeInteger(fraction)) {
    return { ok: false, reason: "format" };
  }
  const amountMinor = lira * 100 + fraction;
  if (amountMinor <= 0) {
    return { ok: false, reason: "non_positive" };
  }
  if (amountMinor > MAX_MINOR) {
    return { ok: false, reason: "format" };
  }
  return { ok: true, amountMinor };
}

/** Kuruş → görüntülenecek TL metni (örn. 1250050 → "12.500,50 ₺"). */
export function formatMinorAsTry(amountMinor: number): string {
  const safe = Number.isFinite(amountMinor) ? Math.trunc(amountMinor) : 0;
  const lira = Math.trunc(safe / 100);
  const kurus = Math.abs(safe % 100);
  const liraText = new Intl.NumberFormat("tr-TR").format(lira);
  return `${liraText},${String(kurus).padStart(2, "0")} ₺`;
}
