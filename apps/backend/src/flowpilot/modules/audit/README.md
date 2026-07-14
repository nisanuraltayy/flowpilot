# modules/audit — Audit

**Sahip olduğu kavramlar:** AuditEvent.
**Sahip olduğu tablolar:** `audit_events` *(append-only)*.

## Sorumluluk

**Audit log FlowPilot'ın ÜRÜN BİLEŞENİDİR**, teknik bir ek değil. "Kim, ne zaman, neyi onayladı?" sorusuna kanıtla cevap veremeyen bir onay ürünü değersizdir.

## Sınırlar (bozulamaz)

- **Append-only.** `UPDATE`/`DELETE` kod yolu **bulunamaz**. Düzeltme gerekiyorsa önceki olaya referans veren **correction event** yazılır.
- **Audit, business transaction başarısızsa YAZILMAZ.** State + outbox + audit **aynı transaction**'dadır. Başarısız bir işlem başarılı gibi görünemez (SPK-11).
- Audit **application log'un yerine geçmez**; application log da audit'in yerine geçmez.
- Hassas değerlerin **tamamı** yazılmaz — maskeleme/hash uygulanır.
- Zorunlu alanlar: `event_id`, `tenant_id`, `actor_type`, `actor_id`, `action`, `resource_type`, `resource_id`, `timestamp` (UTC), `request_id`, `metadata`, `reason`.
- Okuma `audit.read` permission'ı gerektirir ve tenant-scoped'dur.

## Durum

Boş.
