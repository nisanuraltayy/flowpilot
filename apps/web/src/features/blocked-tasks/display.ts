/**
 * Engellenen onay görevi görüntüleme yardımcıları — backend değer → Türkçe metin (SAF).
 *
 * blocked_reason backend'de KÜÇÜK, CHECK ile kısıtlı bir kümedir; şu an tek gerçek değer
 * `self_approval_no_eligible_assignee`. Bilinmeyen/null reason UYDURULMAZ: güvenli genel
 * fallback metni gösterilir. Ham reason değeri kullanıcıya gösterilmek zorunda değildir.
 */

const REASON_LABELS: Record<string, string> = {
  self_approval_no_eligible_assignee: "Kendi talebini onaylama engeli",
};

const REASON_DESCRIPTIONS: Record<string, string> = {
  self_approval_no_eligible_assignee:
    "Görev için belirlenen kullanıcı talebi oluşturan kişi olduğu ve başka uygun onaycı bulunamadığı için görev beklemeye alındı.",
};

const FALLBACK_LABEL = "Atama sorunu";
const FALLBACK_DESCRIPTION =
  "Bu onay görevi uygun bir kullanıcıya atanamadığı için ilerleyemiyor.";

export function blockedReasonLabel(reason: string | null): string {
  return reason !== null ? (REASON_LABELS[reason] ?? FALLBACK_LABEL) : FALLBACK_LABEL;
}

export function blockedReasonDescription(reason: string | null): string {
  return reason !== null ? (REASON_DESCRIPTIONS[reason] ?? FALLBACK_DESCRIPTION) : FALLBACK_DESCRIPTION;
}

const STATUS_LABELS: Record<string, string> = {
  blocked: "Engellendi",
  active: "Aktif",
  pending: "Bekliyor",
  completed: "Tamamlandı",
};

export function taskStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
