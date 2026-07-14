# apps/ — Deployable Birimler

Bu klasördeki her alt dizin **bir composition root**'tur: modülleri birbirine bağlar, portlara adapter enjekte eder ve uygulamayı dış dünyaya açar.

## Bağımlılık sınırı

**MUST:**
- `apps/*` yalnızca `modules/*`'ın **application** katmanına (command/query) ve `packages/*`'a bağımlı olabilir.
- Adapter seçimi (hangi `AuthProviderPort` implementasyonu, hangi `FileStoragePort`) **burada** yapılır.

**MUST NOT:**
- `apps/*` içinde **iş mantığı bulunamaz**. Yetki kararı, koşul değerlendirmesi, onay sırası, state transition → hepsi `modules/`'dadır.
- `apps/*` bir modülün `infrastructure/persistence` katmanını **import edemez**.
- `apps/web` hiçbir backend modülünü import edemez; yalnız `packages/contracts` üzerinden konuşur.

## Alt dizinler

| Dizin | Rol |
|---|---|
| [api/](api/README.md) | FastAPI — senkron HTTP API |
| [worker/](worker/README.md) | Outbox dispatcher, timer worker, event consumer |
| [web/](web/README.md) | Next.js kullanıcı uygulaması |

`api` ve `worker` **ayrı process**'lerdir (ADR-003). Web process'i içinde cron veya in-memory timer çalıştırmak **YASAKTIR**.

## Durum

Boş. Scaffold henüz oluşturulmadı ve owner onayı olmadan oluşturulmayacak.
