/** Üyelik türü → Türkçe etiket (SAF). Bilinmeyen değer güvenli fallback. */

const MEMBERSHIP_KIND_LABELS: Record<string, string> = {
  owner: "Sahip",
  admin: "Yönetici",
  member: "Üye",
};

export function membershipKindLabel(kind: string): string {
  return MEMBERSHIP_KIND_LABELS[kind] ?? kind;
}
