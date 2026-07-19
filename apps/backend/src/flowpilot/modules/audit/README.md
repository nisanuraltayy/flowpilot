# modules/audit — Audit

**Sahip olduğu kavramlar:** `AuditEntry`, `AuditEventType`, `AuditRecord` (application contract).
**Sahip olduğu tablolar:** `audit_entries` *(append-only)*.

## Sorumluluk

**Audit log FlowPilot'ın ÜRÜN BİLEŞENİDİR**, teknik bir ek değil. "Kim, ne zaman, neyi
onayladı?" sorusuna kanıtla cevap veremeyen bir onay ürünü değersizdir.

İlk dilim event türleri: `purchase_request.created`, `workflow.started`,
`approval.task_assigned`, `approval.approved`, `approval.rejected`, `workflow.completed`,
`workflow.rejected`.

## Dışa sunulan sözleşme (cross-module)

Business modüller audit yazarken **`audit.domain`'i IMPORT ETMEZ** (dependency-rules §2).
Yazma yalnız application contract üzerinden yapılır:

- `AuditWriterPort.append(record: AuditRecord)` — `AuditRecord` primitive + UUID taşıyan
  application DTO'sudur; `event_id` çağıranın injectable `IdGeneratorPort`'undan gelir.
  `AuditEventType` `audit.application.dto`'dan re-export edilir.
- `AuditTimelineQueryPort.list_for_aggregate(...)` — bir aggregate'in kronolojik,
  tenant-scoped timeline'ı (`AuditTimelineItem`; kullanıcıya güvenli mesaj).
- Writer, `AuditRecord`'u içeride `AuditEntry` (domain) üzerinden satıra map eder.
  Presentation/API katmanı audit tablosuna **DOĞRUDAN insert YAPMAZ**.

## Sınırlar (bozulamaz)

- **Append-only.** `UPDATE`/`DELETE` kod yolu **bulunamaz**. DB'de iki katman: app rolüne
  UPDATE/DELETE grant'i verilmez **ve** `audit_block_mutation` BEFORE UPDATE/DELETE
  trigger'ı her mutasyonu reddeder. Düzeltme gerekiyorsa önceki olaya referans veren
  **correction event** yazılır.
- **Audit, business transaction başarısızsa YAZILMAZ.** State + outbox + audit **aynı
  transaction**'dadır (compose UoW). Başarısız bir işlem başarılı gibi görünemez (SPK-11).
- **Deterministik sıra:** `seq BIGINT GENERATED ALWAYS AS IDENTITY` kolonu ile aynı
  `occurred_at` içinde bile insertion order korunur (timeline `(occurred_at, seq)` sırasıyla
  döner) — clock'a bağlı değildir.
- **RLS ENABLE + FORCE** + tenant policy; context yoksa default deny. Başka tenant'ın
  timeline'ı görünmez.
- Hassas değerler (token/secret/e-posta) `metadata`'ya **yazılmaz** — sınırlı, güvenli alanlar.
- Audit **application log'un yerine geçmez**; application log da audit'in yerine geçmez.

## Durum

**Uygulanmış (backend).** Append-only writer (same-tx), timeline read model ve purchase
request/approval akışlarıyla entegrasyon. Correction event ve `audit.read` permission'ı
sonraki dilimlerde.
