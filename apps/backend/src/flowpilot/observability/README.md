# flowpilot.observability — Log, Metric, Trace

Vendor-neutral gözlemlenebilirlik sözleşmeleri (OpenTelemetry yaklaşımı).

## İçerik (üretilecek)

- **Structured JSON log** — her satırda `request_id`, `correlation_id`, `tenant_id`, `actor_id`
- **PII redaction** — Restricted/Secret sınıfı veriler log'a **yazılmaz**
- **Metric** sözleşmeleri — API latency/error, outbox lag, worker lag, timer gecikmesi, retry sayısı, `authorization_denied_total`, `duplicate_event_suppressed_total`
- **Trace** — API request → DB → outbox publish → worker processing zinciri

## Sınırlar

- **Application log, audit log'un yerine geçmez** ve tersi de doğru değildir. Audit bir üründür; log bir operasyon aracıdır.
- Secret, token ve kişisel veri **loglanamaz**.
- Bu paket hiçbir modüle bağımlı olamaz.

## Durum

Boş.
