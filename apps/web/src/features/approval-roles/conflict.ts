/**
 * Onay rolü atama çakışma/doğrulama sınıflandırması (SAF, IO yok — test edilebilir).
 *
 * Backend iş çakışmalarını 409 + ham Türkçe domain detay'ı, doğrulama hatalarını 422 + ham
 * detay ile döndürür. Ham detay KULLANICIYA GÖSTERİLMEZ; ayırt edici kararlı belirteçlerle
 * güvenli sabit mesajlara eşlenir. Sınıflandırılamayan durum güvenli genel mesaj alır.
 * Belirteç eşleşmesi yalnız sınıflandırma içindir; ham metin ekrana basılmaz.
 *
 * Gerçek backend mesajları (role_assignment_handlers.py / repository):
 * - 409 "hedef üyelik aktif değil — atanamaz"            → invalid_member_status
 * - 409 "stale expected_version"                          → stale
 * - 409 "atama eşzamanlı değişti (stale version)"         → stale
 * - 409 "aktif atama zaten var (eşzamanlı atama)"         → stale
 * - 422 "geçersiz role_key: ..."                          → invalid_role
 * - 422 "mevcut atama var; expected_version gerekli"      → stale (frontend version'ı yenilemeli)
 */

export type ApprovalRoleConflictKind =
  | "stale"
  | "invalid_member_status"
  | "invalid_role"
  | "conflict";

export const STALE_MESSAGE =
  "Bu onay rolü başka bir işlem tarafından güncellendi. Liste yenilendi; lütfen tekrar deneyin.";
export const INVALID_MEMBER_STATUS_MESSAGE =
  "Yalnızca aktif organizasyon üyeleri onay rolüne atanabilir.";
export const INVALID_ROLE_MESSAGE = "Seçilen onay rolü desteklenmiyor.";
export const GENERIC_CONFLICT_MESSAGE =
  "Onay rolü ataması güncellenemedi. Listeyi yenileyip tekrar deneyin.";

export function classifyApprovalRoleConflict(rawDetail: string): {
  kind: ApprovalRoleConflictKind;
  message: string;
} {
  const d = rawDetail.toLocaleLowerCase("tr");
  if (d.includes("stale") || d.includes("eşzamanlı") || d.includes("expected_version")) {
    return { kind: "stale", message: STALE_MESSAGE };
  }
  if (d.includes("aktif değil")) {
    return { kind: "invalid_member_status", message: INVALID_MEMBER_STATUS_MESSAGE };
  }
  if (d.includes("role_key")) {
    return { kind: "invalid_role", message: INVALID_ROLE_MESSAGE };
  }
  return { kind: "conflict", message: GENERIC_CONFLICT_MESSAGE };
}
