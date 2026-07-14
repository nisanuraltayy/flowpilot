# modules/notification — Notification

**Sahip olduğu kavramlar:** Notification.
**Sahip olduğu tablolar:** `notifications`.

## Sorumluluk

Outbox event'lerinden üretilen, tenant-scoped, deduplike edilmiş bildirim.

## Sınırlar

- **`NotificationChannelPort` KANAL-NÖTR tasarlanır.** MVP'de yalnız **in-app adapter** uygulanır. E-posta eklemek bir **adapter eklemek** olmalıdır — bir refactor değil ([ASM-0010](../../../../../../docs/assumptions.md)).
- **Bu modül hiçbir iş modülünü import etmez.** `approval_steps`, `tasks` gibi tabloları **okuyamaz**; ihtiyacı olan veriyi **event payload'ından** alır. Bu, modülü ileride ayrı bir servise çıkarmayı mümkün kılar.
- **Duplicate bildirim üretilemez.** Aynı business event + recipient + kanal → tek bildirim (`dedup_key` unique constraint).
- Bildirim payload'ında **gereksiz hassas veri taşınmaz**.
- Deep link **yetkiyi bypass etmez** — hedef sayfada authorization yeniden çalışır.

## ⚠️ Kabul edilmiş risk

MVP'de e-posta yoktur. Onaycı uygulamaya girmezse bekleyen onayı fark etmeyebilir — bu, ürünün çözmeye çalıştığı gecikme probleminin farklı bir biçimde geri gelmesidir. Risk owner tarafından kabul edilmiş ve **pilot-ready çıkış kriteri** olarak izlenmektedir.

## Durum

Boş.
