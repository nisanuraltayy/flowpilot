/**
 * Davet görüntüleme yardımcıları — backend kod → Türkçe etiket (SAF, IO yok).
 *
 * Backend'in DÖNDÜRMEDİĞİ durum/rol UYDURULMAZ: bilinmeyen değer güvenli biçimde
 * ham hâliyle gösterilir (sessiz yanlış etiket yerine dürüst fallback). Backend liste
 * bugün yalnız `pending` döndürür; diğer durumlar (önizleme/ileri uyum) için de etiket
 * hazırdır.
 */

import type { BadgeTone } from "@/features/purchase-requests/display";

export type { BadgeTone } from "@/features/purchase-requests/display";

const STATUS_LABELS: Record<string, string> = {
  pending: "Bekliyor",
  accepted: "Kabul edildi",
  revoked: "İptal edildi",
  expired: "Süresi doldu",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  pending: "pending",
  accepted: "success",
  revoked: "neutral",
  expired: "error",
};

const ROLE_LABELS: Record<string, string> = {
  admin: "Yönetici",
  member: "Üye",
};

export function invitationStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function invitationStatusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? "neutral";
}

export function invitationRoleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

/** Yalnız bekleyen davet iptal (revoke) edilebilir. */
export function isInvitationRevocable(status: string): boolean {
  return status === "pending";
}
