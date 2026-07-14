# apps/ — Deployable Birimler

| Dizin | Rol |
|---|---|
| [backend/](backend/README.md) | **Tek Python distribution** (`flowpilot-backend`). İçinde 13 bounded context ve **iki composition root**: `flowpilot.api` ve `flowpilot.worker` |
| [web/](web/README.md) | Next.js kullanıcı uygulaması |

Fiziksel yerleşim kararı: [ADR-009](../docs/adr/ADR-009-python-physical-layout.md).

## Backend: tek distribution, iki process

`api` ve `worker` **ayrı Python projeleri değildir**. Aynı distribution içindeki iki entrypoint'tir:

- `flowpilot.api` → `flowpilot.api.main:app` (uvicorn)
- `flowpilot.worker` → `python -m flowpilot.worker`

İkisi de **aynı domain/application kodunu** kullanır (ADR-003). Aynı Docker image, farklı `CMD`. Web process'i içinde cron veya in-memory timer çalıştırmak **YASAKTIR**.

## Bağımlılık sınırı

**MUST NOT:**
- **`flowpilot.api` ve `flowpilot.worker` içinde iş mantığı bulunamaz.** Yetki kararı, koşul değerlendirmesi, onay sırası ve state transition → hepsi `flowpilot.modules.*`'dadır.
- Composition root'lar modüllerin `domain` veya `infrastructure` katmanını **doğrudan import edemez** — tek istisna adapter wiring'dir ve tek dosyada toplanır (`api/deps.py`, `worker/wiring.py`).
- `apps/web` hiçbir backend modülünü import edemez; yalnız [`packages/contracts`](../packages/contracts/README.md) üzerinden konuşur.

**MUST:**
- Composition root'lar **yalnız `flowpilot.modules.*.application`** sınırlarını çağırır.
- Adapter seçimi (hangi `AuthProviderPort`, hangi `FileStoragePort`) **yalnız composition root'ta** yapılır.

## Durum

Boş. Scaffold henüz oluşturulmadı ve owner onayı olmadan oluşturulmayacak.
