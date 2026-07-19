/** Tarih/zaman gösterimi — UTC ISO string → tr-TR yerel gösterim. */

const FORMATTER = new Intl.DateTimeFormat("tr-TR", {
  dateStyle: "medium",
  timeStyle: "short",
});

/** ISO-8601 (UTC) zaman damgasını okunaklı Türkçe metne çevirir; geçersizse ham döner. */
export function formatDateTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return FORMATTER.format(parsed);
}
