# modules/platform — Platform (paylaşılan altyapı davranışı)

**Sahip olduğu kavramlar:** Transactional Outbox, Idempotent Inbox, Idempotency Key.
**Sahip olduğu tablolar:** `outbox_events`, `processed_events`, `idempotency_keys`.

## Sorumluluk

Asenkron işlemin **güvenilirlik altyapısı** (ADR-007). Tüm modüller event yayınlamak için buradaki outbox sözleşmesini kullanır.

## Sınırlar

- **Dual write YASAK.** Business state değişikliği ve integration event **aynı transaction'da** `outbox_events`'e yazılır. Commit olmazsa event de olmaz; commit olursa event **kesinlikle** vardır.
- Dispatcher `FOR UPDATE SKIP LOCKED` + lease/visibility timeout ile çalışır; iki worker aynı event'i iki kez dağıtmaz.
- Consumer'lar **idempotent**tir: işlenen `event_id` `processed_events`'e, **side effect ile aynı transaction'da** yazılır. Aksi hâlde crash sonrası duplicate side effect oluşur.
- **Sonsuz retry YASAK.** Exponential backoff + jitter, maksimum attempt, ardından dead-letter/incident.
- **`"exactly once"` iddiası YASAK.** Yaklaşım: at-least-once delivery + idempotent consumer.
- Event tipi **versiyonludur** (`approval.decided.v1`); mevcut version'ın payload semantiği değiştirilmez.
- Her event `tenant_id` ve `correlation_id` taşır.
- Outbox retention/temizleme job'ı tanımlıdır — tablo sınırsız büyüyemez.

> Not: Bu modül PRD §35.1'de ayrı bir bounded context olarak listelenmemiştir; outbox/inbox/idempotency tablolarının bir sahibi olması gerektiği için ayrılmıştır. Bir iş domain'i **değildir**; iş mantığı içermez.

## Durum

Boş.
