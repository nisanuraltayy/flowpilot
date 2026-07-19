/**
 * Görüntüleme yardımcıları — backend kod → Türkçe etiket eşlemeleri (SAF).
 *
 * Backend'in DÖNDÜRMEDİĞİ durum/rol/event UYDURULMAZ: bilinmeyen değer güvenli
 * biçimde ham hâliyle gösterilir (sessiz yanlış etiket yerine dürüst fallback).
 */

export type BadgeTone = "success" | "error" | "pending" | "neutral";

const STATUS_LABELS: Record<string, string> = {
  draft: "Taslak",
  in_approval: "Onay bekliyor",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  draft: "neutral",
  in_approval: "pending",
  approved: "success",
  rejected: "error",
  cancelled: "neutral",
};

const ROLE_LABELS: Record<string, string> = {
  team_manager: "Ekip yöneticisi",
  finance: "Finans",
  general_manager: "Genel müdür",
};

const EVENT_LABELS: Record<string, string> = {
  "purchase_request.created": "Talep oluşturuldu",
  "workflow.started": "Onay süreci başlatıldı",
  "approval.task_assigned": "Onay görevi atandı",
  "approval.approved": "Talep adımı onaylandı",
  "approval.rejected": "Talep reddedildi",
  "workflow.completed": "Onay süreci tamamlandı",
  "workflow.rejected": "Süreç reddedilerek sonlandı",
};

export function purchaseRequestStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function purchaseRequestStatusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? "neutral";
}

export function approvalRoleLabel(role: string | null): string | null {
  if (role === null) {
    return null;
  }
  return ROLE_LABELS[role] ?? role;
}

export function timelineEventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType;
}
