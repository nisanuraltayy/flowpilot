/**
 * Üye mutasyonu 409 sınıflandırması (SAF, IO yok — bu yüzden test edilebilir).
 *
 * Backend TÜM bu çakışmaları 409 + ham Türkçe domain detay'ı ile döndürür. Ham detay
 * KULLANICIYA GÖSTERİLMEZ; burada ayırt edici, KARARLI belirteçlerle güvenli sabit mesajlara
 * eşlenir. Sınıflandırma başarısız olursa (bilinmeyen 409) güvenli genel çakışma mesajı döner.
 * Belirteç eşleşmesi yalnız sınıflandırma içindir; ham metin hiçbir zaman ekrana basılmaz.
 */

export type MemberConflictKind =
  | "stale"
  | "self"
  | "final_owner"
  | "approval_responsibility"
  | "removed"
  | "invalid_transition"
  | "conflict";

export const STALE_MESSAGE =
  "Bu üye başka bir işlem tarafından güncellendi. Liste yenilendi; lütfen tekrar deneyin.";
export const SELF_MESSAGE = "Kendi rolünüzü veya üyelik durumunuzu değiştiremezsiniz.";
export const FINAL_OWNER_MESSAGE =
  "Organizasyonda en az bir aktif sahip bulunmalıdır. Önce başka bir kullanıcıyı sahip yapın.";
export const APPROVAL_RESP_MESSAGE =
  "Bu kullanıcının aktif onay sorumlulukları bulunuyor. Önce bu sorumlulukları başka bir kullanıcıya atayın.";
export const REMOVED_MESSAGE = "Kaldırılmış bir üyelik yeniden değiştirilemez.";
export const INVALID_TRANSITION_MESSAGE = "Bu üyelik için seçilen durum değişikliği uygulanamaz.";
export const GENERIC_CONFLICT_MESSAGE =
  "Bu işlem şu anda tamamlanamadı (çakışma). Listeyi yenileyip tekrar deneyin.";

export function classifyMemberConflict(rawDetail: string): {
  kind: MemberConflictKind;
  message: string;
} {
  const d = rawDetail.toLocaleLowerCase("tr");
  if (d.includes("stale") || d.includes("eşzamanlı")) {
    return { kind: "stale", message: STALE_MESSAGE };
  }
  if (d.includes("kendi")) {
    return { kind: "self", message: SELF_MESSAGE };
  }
  if (d.includes("owner")) {
    return { kind: "final_owner", message: FINAL_OWNER_MESSAGE };
  }
  if (d.includes("onay sorumlulu")) {
    return { kind: "approval_responsibility", message: APPROVAL_RESP_MESSAGE };
  }
  if (d.includes("kaldır")) {
    return { kind: "removed", message: REMOVED_MESSAGE };
  }
  if (d.includes("geçiş")) {
    return { kind: "invalid_transition", message: INVALID_TRANSITION_MESSAGE };
  }
  return { kind: "conflict", message: GENERIC_CONFLICT_MESSAGE };
}
