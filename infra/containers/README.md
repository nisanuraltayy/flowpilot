# infra/containers — Local Development Altyapısı

> ⚠️ **YALNIZCA LOCAL DEVELOPMENT VE INTEGRATION TESTİ İÇİNDİR.** Production deployment değildir.

[compose.yaml](compose.yaml) iki servis çalıştırır: **PostgreSQL** (tek source of truth) ve **MinIO** (S3-compatible object storage).

Bu aşamada uygulama bu servislere **bağlanmaz**. Schema, tablo, migration, RLS policy, bucket veya access policy **yoktur**.

## Kullanılan imajlar (pinned — `latest` YASAK)

| Servis | Imaj | Gerekçe |
|---|---|---|
| PostgreSQL | `postgres:17.10-alpine` | ADR-006 (RLS) ve ADR-007 (`FOR UPDATE SKIP LOCKED`) PostgreSQL'e özgü davranışlara dayanır. 17, bu yeteneklerin olgun ve geniş desteklendiği kararlı major sürümdür. Alpine küçük imaj. |
| MinIO | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | S3-compatible storage; `FileStoragePort`'un local adayı (ASM-0006). Sabit release tag'i ile pinlenmiştir. |

## Önkoşullar

- Docker Desktop çalışıyor (`docker info` hatasız dönmeli).
- Boş portlar: **5432** (PostgreSQL), **9000** (MinIO API), **9001** (MinIO Console).

## Environment hazırlığı

Compose, secret'ları environment'tan okur; hiçbir secret compose dosyasında **hard-code edilmez**. Değişken eksikse Compose **anlaşılır hata** verip başlamaz.

Repo kökünde bir `.env` oluşturun (bu dosya `.gitignore` ile **dışlanır, commit edilmez**). Şablon: [.env.example](../../.env.example) §2 ve §2b.

```powershell
# Repo kökünde — örnek şablondan kopyalayıp local parolaları girin.
Copy-Item .env.example .env
# .env içinde POSTGRES_PASSWORD ve MINIO_ROOT_PASSWORD değerlerini girin.
# MinIO parolası en az 8 karakter olmalıdır.
```

Gerekli değişkenler: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`.

> **`.env` değerleri yalnızca local development içindir.** Production credential değildir; öyle kullanılmamalıdır.

## Komutlar (Windows PowerShell)

Tüm komutlar **repo kökünden** çalıştırılır.

```powershell
# Compose'u doğrula (secret'ları terminale yazdırmadan yapıya bakın)
docker compose --env-file .env -f infra/containers/compose.yaml config

# Servisleri başlat (arka planda)
docker compose --env-file .env -f infra/containers/compose.yaml up -d

# Durum (health dahil)
docker compose --env-file .env -f infra/containers/compose.yaml ps

# Logları izle (Ctrl+C ile çık)
docker compose --env-file .env -f infra/containers/compose.yaml logs -f
docker compose --env-file .env -f infra/containers/compose.yaml logs -f postgres   # tek servis

# Durdur — VERİYİ KORUYARAK (named volume'lar kalır)
docker compose --env-file .env -f infra/containers/compose.yaml down

# Tamamen SIFIRLA — volume'ları da SİL (tüm veri gider)
docker compose --env-file .env -f infra/containers/compose.yaml down -v
```

## Healthcheck komutları

```powershell
# PostgreSQL — accepting connections beklenir
docker exec flowpilot-postgres-1 pg_isready -U flowpilot_admin -d flowpilot

# MinIO — HTTP 200 beklenir
docker exec flowpilot-minio-1 curl -f http://localhost:9000/minio/health/live
```

Compose healthcheck'leri: PostgreSQL `pg_isready`, MinIO `/minio/health/live`. İkisi de `interval 5s / timeout 5s / retries 10 / start_period 10s`.

## PostgreSQL bağlantı bilgileri

| | Değer |
|---|---|
| Host / Port | `localhost:5432` |
| Database | `flowpilot` |
| Rol | `.env`'deki `POSTGRES_USER` (varsayılan `flowpilot_admin`) |

> **Bu bootstrap rolü bir ADMIN/superuser rolüdür — UYGULAMA BUNUNLA BAĞLANMAZ.** PostgreSQL resmi imajı `POSTGRES_USER`'ı her zaman superuser yapar; superuser RLS'i bypass eder. ADR-006 gereği uygulamanın bağlanacağı **BYPASSRLS'siz** `flowpilot_app` rolü, PostgreSQL database foundation / Alembic aşamasında ayrıca oluşturulacaktır. Şu an o rol **yoktur** ve bu aşamada oluşturulmaz.

## MinIO adresleri

| | Adres |
|---|---|
| S3 API | `http://localhost:9000` |
| Web Console | `http://localhost:9001` |
| Kök kullanıcı | `.env`'deki `MINIO_ROOT_USER` |

## Veri ve güvenlik

- **Veriler named volume'da tutulur:** `flowpilot-postgres-data` ve `flowpilot-minio-data`. **Repository içine bind mount EDİLMEZ** — `down -v` dışında repo'ya veri sızmaz, `git status` kirlenmez.
- **Secret güvenliği:** parolalar yalnız `.env`'de (git-ignored). Compose dosyasında hard-code **yok**. `docker compose config` çıktısı secret içerir — **paylaşmayın, commit'e kopyalamayın**.
- **Container sertleştirmesi:** `no-new-privileges:true`; `privileged`, host network, Docker socket mount, ek capability **yok**.
- **`.env` asla commit edilmez** (`.gitignore`).

## Servisler ayaktayken: roller ve migration

Database foundation aşamasıyla birlikte roller ve şema **artık script/migration ile kurulur**:

```powershell
# Rolleri provision et (flowpilot_migrator + flowpilot_app; idempotent)
.\.venv\Scripts\python.exe scripts/provision_local_database.py

# Migration'ları uygula (flowpilot_migrator rolüyle)
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
```

Rol ayrımı ve RLS ayrıntısı: [apps/backend/README.md](../../apps/backend/README.md).

## Bu aşamada hâlâ YOK

MinIO bucket, access policy, presigned URL/SDK kodu, uygulamanın MinIO bağlantısı, HTTP endpoint'leri, Dockerfile/backend image — **hiçbiri**.
