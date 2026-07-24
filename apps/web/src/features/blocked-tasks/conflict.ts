/**
 * Engellenen görev çözümleme çakışma sınıflandırması (SAF, IO yok — test edilebilir).
 *
 * Backend TÜM çözümleme çakışmalarını 409 + ham Türkçe domain detay'ı ile döndürür. Ham detay
 * KULLANICIYA GÖSTERİLMEZ; ayırt edici kararlı belirteçlerle güvenli sabit mesajlara eşlenir.
 * Sınıflandırılamayan durum güvenli genel mesaj alır. Belirteç eşleşmesi yalnız sınıflandırma
 * içindir; ham metin ekrana basılmaz.
 *
 * Gerçek backend mesajları (blocked_task_handlers.py):
 * - "task self-approval nedeniyle blocked değil"                       → not_blocked
 * - "{role} için aktif rol ataması yok — önce atama yapılmalı"         → no_assignment
 * - "aday aktif üye değil — atanamaz"                                  → candidate_inactive
 * - "çözümleme çakışması" (concurrency/self-approval/terminal)         → conflict (liste yenilenir)
 */

export type BlockedTaskConflictKind =
  | "not_blocked"
  | "no_assignment"
  | "candidate_inactive"
  | "conflict";

export const NOT_BLOCKED_MESSAGE =
  "Bu onay görevi artık atama beklemiyor. Liste yenilendi.";
export const NO_ASSIGNMENT_MESSAGE =
  "Bu görev için gerekli onay rolüne atanmış aktif bir kullanıcı yok. Önce Onay Rolleri sayfasından bir kullanıcı atayın.";
export const CANDIDATE_INACTIVE_MESSAGE =
  "Bu göreve atanacak kullanıcı artık aktif değil. Onay rolü atamasını güncelleyin.";
export const GENERIC_CONFLICT_MESSAGE =
  "Onay görevinin atama sorunu çözülemedi. Listeyi yenileyip tekrar deneyin.";

export function classifyBlockedTaskConflict(rawDetail: string): {
  kind: BlockedTaskConflictKind;
  message: string;
} {
  const d = rawDetail.toLocaleLowerCase("tr");
  if (d.includes("blocked değil")) {
    return { kind: "not_blocked", message: NOT_BLOCKED_MESSAGE };
  }
  if (d.includes("ataması yok") || d.includes("atama yapılmalı")) {
    return { kind: "no_assignment", message: NO_ASSIGNMENT_MESSAGE };
  }
  if (d.includes("aday")) {
    return { kind: "candidate_inactive", message: CANDIDATE_INACTIVE_MESSAGE };
  }
  return { kind: "conflict", message: GENERIC_CONFLICT_MESSAGE };
}
