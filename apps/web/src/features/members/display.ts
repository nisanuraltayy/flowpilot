/**
 * Üye görüntüleme yardımcıları — backend kod → Türkçe etiket (SAF, IO yok).
 *
 * Backend'in DÖNDÜRMEDİĞİ rol/durum UYDURULMAZ: bilinmeyen değer güvenli biçimde ham
 * hâliyle gösterilir (sessiz yanlış etiket yerine dürüst fallback). Rozetlerde renk TEK
 * BAŞINA anlam taşımaz; metin etiket daima görünür.
 */

import type { BadgeTone } from "@/features/purchase-requests/display";

export type { BadgeTone } from "@/features/purchase-requests/display";

const ROLE_LABELS: Record<string, string> = {
  owner: "Sahip",
  admin: "Yönetici",
  member: "Üye",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Aktif",
  suspended: "Askıya alındı",
  removed: "Kaldırıldı",
  // Tarihsel/ileri uyum: backend bu durumu döndürürse güvenli etiket.
  invited: "Davet edildi",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  active: "success",
  suspended: "pending",
  removed: "neutral",
  invited: "pending",
};

export function memberRoleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

export function memberStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function memberStatusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? "neutral";
}

/** Email null olabilir; listede güvenli, kimlik sızdırmayan yer tutucu gösterilir. */
export function memberEmailLabel(email: string | null): string {
  return email !== null && email !== "" ? email : "E-posta bilgisi yok";
}
