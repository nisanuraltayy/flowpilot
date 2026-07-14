# flowpilot.worker — Asenkron İşlem Process'i

**Rol:** Composition root. `api`'den **ayrı bir process**'tir (ADR-003). Transactional outbox'ı tüketir, timer'ları ateşler, event handler'ları çalıştırır.

## Sorumlulukları

- **Outbox dispatcher** — `outbox_events` tablosunu `FOR UPDATE SKIP LOCKED` ile güvenli okur, handler'lara dağıtır, işlenmiş olarak işaretler (ADR-007)
- **Timer worker** — vadesi gelen persisted timer'ları lease mekanizmasıyla ateşler
- **Event consumer'lar** — notification üretimi, read model projection'ı
- Bounded retry (exponential backoff + jitter) ve dead-letter/incident yönetimi

## Bağımlılık sınırı

**MUST:**
- Her handler **idempotency davranışını tanımlar** ve `processed_events` (inbox) ile duplicate side effect'i engeller (FF-07).
- Idempotency işareti, side effect ile **aynı transaction'da** yazılır.
- Worker DB session'ını **tenant context ile** açar ve **RLS'e tabidir**. `BYPASSRLS` yetkili rol kullanmak, en sinsi cross-tenant sızıntı yoludur — **YASAK** (SPK-10).
- Terminal instance guard'ı **worker yolunda da** uygulanır; event handler bir arka kapı olamaz (SPK-09).

**MUST NOT:**
- **Sonsuz retry YASAK.** Maksimum attempt ve maksimum toplam süre tanımlıdır.
- In-memory timer **YASAK**; timer'lar veritabanındadır.
- `"exactly once"` iddiası **YASAK**. Yaklaşım: at-least-once delivery + idempotent consumer.

## Durum

Boş. Kaynak kodu **henüz oluşturulmadı**. Runtime'a bağlı kod, workflow runtime spike'ının 12/12 exit criterion'u geçmeden yazılamaz (ADR-004, LOCK-003).
