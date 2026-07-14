# infra/containers — Container Tanımları

## İçerik (üretilecek)

- `api.Dockerfile` — FastAPI
- `worker.Dockerfile` — outbox/timer worker
- `web.Dockerfile` — Next.js
- `docker-compose.yml` — local geliştirme: **PostgreSQL** + **MinIO**

## Local geliştirme servisleri

| Servis | Port | Neden gerekli |
|---|---|---|
| PostgreSQL | 5432 | Tek source of truth. RLS (ADR-006), transactional outbox (ADR-007) ve custom workflow runtime (ADR-004) — hepsi PostgreSQL davranışına dayanır. Bu yüzden gerçek bir PostgreSQL olmadan integration testleri anlamsızdır. |
| MinIO | 9000 | S3-compatible object storage — `FileStoragePort` adapter'ı (ASM-0006) |

Preflight'ta 3000, 8000 ve 5432 portlarının boş olduğu doğrulandı.

## Kurallar

- **Container'lar provider-neutral kalır.** Hosting sağlayıcısına özgü yapılandırma eklenmez (LOCK-006 açık).
- Local volume verisi (`data/`, `volumes/`) **`.gitignore`'dadır** — veritabanı içeriği commit edilmez.
- Uygulama container'ı veritabanına **`BYPASSRLS` yetkisi olmayan** rolle bağlanır. Migration için ayrı DDL rolü kullanılır.
- Compose dosyası **gerçek secret içermez**; değerler `.env`'den okunur.

## Durum

Boş. Bu aşamada Dockerfile ve compose **bilinçli olarak oluşturulmadı**.
