/**
 * Onay rolü görüntüleme yardımcıları — backend role_key → Türkçe etiket/açıklama (SAF).
 *
 * Backend approval role_key seti (workflow onay sorumlulukları): team_manager, finance,
 * general_manager. Bunlar org-yönetişim rolünden (owner/admin/member) AYRIDIR. Bilinmeyen
 * role_key UYDURULMAZ: ham hâliyle gösterilir (dürüst fallback). Açıklamalar backend
 * workflow mantığıyla hizalı genel ifadelerdir (eşik/koşul iddiası içermez).
 */

/** Backend'in listelediği/atadığı sabit sıra: team_manager → finance → general_manager. */
export const APPROVAL_ROLE_KEYS = ["team_manager", "finance", "general_manager"] as const;

const ROLE_LABELS: Record<string, string> = {
  team_manager: "Takım Yöneticisi",
  finance: "Finans Sorumlusu",
  general_manager: "Genel Müdür",
};

const ROLE_DESCRIPTIONS: Record<string, string> = {
  team_manager: "Talebi oluşturan ekip veya iş birimi seviyesindeki ilk onayı verir.",
  finance: "Bütçe ve finansal uygunluk adımındaki talepleri değerlendirir.",
  general_manager: "Yüksek tutarlı veya son onay gerektiren talepleri değerlendirir.",
};

export function approvalRoleLabel(roleKey: string): string {
  return ROLE_LABELS[roleKey] ?? roleKey;
}

export function approvalRoleDescription(roleKey: string): string {
  return ROLE_DESCRIPTIONS[roleKey] ?? "";
}
