# tests/integration — Integration Testleri

**Gerçek PostgreSQL** gerektirir (Docker). Fake'e karşı yeşil olan bir test, burada kırmızı olabilir — asıl değer budur.

## Kapsam

- **Transaction sınırları:** state + outbox + audit **aynı transaction'da** (fault injection ile: rollback → dört tablo da boş)
- **Transactional outbox:** yazım ve polling worker dispatch'i
- **Idempotent inbox:** aynı event iki kez → **tek** side effect
- **Duplicate approval:** eşzamanlı iki komut → **tek** karar (DB-level unique constraint)
- **Optimistic concurrency:** çakışma → 409/412, sessiz overwrite yok
- **Row Level Security:** politikaların gerçekten uygulandığı; uygulama filtresi kaldırılsa bile RLS sorguyu boşa düşürür
- **Worker'ın RLS'e tabi olduğu** (`BYPASSRLS` kullanmadığı)
- **Persisted timer:** restart sonrası **tam bir kez** ateşlenir
- **Terminal guard:** terminal instance API/event/timer yollarının hiçbirinden ilerletilemez
- `FileStoragePort` adapter'ı (MinIO)

## Kural

Workflow runtime **mock'lanamaz**. Gerçek runtime ve gerçek veritabanı kullanılır.

## Durum

Boş.
