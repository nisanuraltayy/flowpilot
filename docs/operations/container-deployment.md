# FlowPilot — Container Deployment (Provider-Neutral)

> **Kapsam:** FP-OPS-001. Bu belge FlowPilot'ın **sağlayıcıdan bağımsız** biçimde nasıl
> paketlendiğini ve çalıştırıldığını anlatır. **Hosting sağlayıcısı seçmez** ve
> [ADR-010](../adr/ADR-010-initial-hosting-and-data-region.md) / LOCK-006 kararlarını
> **değiştirmez**. Sağlayıcıya özel manifest (render.yaml, vercel.json, fly.toml …)
> bilinçli olarak **yoktur**.
>
> Tamamlayıcı belgeler: [deployment-runbook.md](deployment-runbook.md) (ortam envanteri,
> rollback, incident) ve [worker-operations.md](worker-operations.md) (worker servis modu,
> heartbeat, healthcheck ve operasyon prosedürleri) ve [http-security.md](http-security.md)
> (TrustedHost, docs kapatma, API güvenlik header'ları). Bu belge yalnız **container paketleme
> ve çalıştırma** katmanıdır.

## 1. Bileşenler ve image'lar

| Bileşen | Build context | Image | Process |
|---|---|---|---|
| API (FastAPI) | `apps/backend` | `apps/backend/Dockerfile` | `uvicorn flowpilot.api.main:app` |
| Web (Next.js) | `apps/web` | `apps/web/Dockerfile` | `node server.js` (standalone) |
| Worker | `apps/backend` | `apps/backend/Dockerfile` — **`--target worker-runtime`** | `python -m flowpilot.worker --serve` |
| PostgreSQL | — | Managed servis | Container içinde **tutulmaz** (bkz. §8) |

API ve worker **aynı image ailesindendir**: tek Python distribution'ın iki composition
root'u (ADR-009), ortak `runtime` katmanını paylaşırlar. `api` stage'i Dockerfile'ın
**en sonundadır**, bu yüzden `--target` verilmeden yapılan build **API** üretir; worker
hiçbir koşulda default process değildir. İkisi **ayrı servis** olarak çalıştırılır —
tek container'da birleştirilmez.

Her iki context de **kendi kendine yeterlidir**: `apps/backend` tek Python distribution'dır
(ADR-009), `apps/web` kendi `package.json` + `package-lock.json`'ına sahiptir. Monorepo
kökünü build context yapmaya gerek yoktur.

## 2. Image build

```bash
docker build -t flowpilot-api:<tag> apps/backend
```

```bash
docker build --target worker-runtime -t flowpilot-worker:<tag> apps/backend
```

```bash
docker build -t flowpilot-web:<tag> \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=<public-supabase-url> \
  --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key> \
  --build-arg NEXT_PUBLIC_APP_URL=<public-app-url> \
  apps/web
```

> **Kritik:** `NEXT_PUBLIC_*` değerleri Next.js tarafından **build sırasında koda gömülür**.
> Runtime'da `-e` ile verilmeleri **etkisizdir**. Değiştirmek için **yeniden build** gerekir.
> Bu değerler secret değildir (tarayıcıya gider); yine de gerçek değerler repository'ye yazılmaz.

## 3. Container run

```bash
docker run -d --name flowpilot-api -p 8000:8000 \
  -e APP_ENVIRONMENT=production \
  -e APP_DEBUG=false \
  -e DATABASE_URL=<app-role-connection-string> \
  -e SUPABASE_URL=<supabase-project-url> \
  flowpilot-api:<tag>
```

```bash
docker run -d --name flowpilot-worker \
  -e APP_ENVIRONMENT=production \
  -e DATABASE_URL=<app-role-connection-string> \
  -e WORKER_TENANT_IDS=<tenant-uuid[,tenant-uuid...]> \
  flowpilot-worker:<tag>
```

Worker **HTTP portu dinlemez** (`-p` yoktur) ve `WORKER_TENANT_IDS` boşsa **kontrollü hata**
ile çıkar — sessizce boş çalışmaz. Worker cross-tenant keşif yapmaz: uygulama rolü
`flowpilot_app` NOBYPASSRLS'tir, bu yüzden işlenecek tenant'lar **açıkça** verilir.

```bash
docker run -d --name flowpilot-web -p 3000:3000 \
  -e FLOWPILOT_API_BASE_URL=<api-base-url> \
  flowpilot-web:<tag>
```

Portlar environment'tan gelir: API `APP_PORT` (default 8000), Web `PORT` (default 3000).
Her ikisi de `0.0.0.0` dinler ve **non-root** çalışır (API uid `10001`, Web `node`/uid `1000`).

## 4. Runtime environment değişkenleri (yalnız ADLAR)

### API (runtime)

| Değişken | Zorunlu | Not |
|---|---|---|
| `APP_ENVIRONMENT` | ✅ | `production` / `staging` → strict doğrulama açılır |
| `DATABASE_URL` | ✅ | Uygulama rolü `flowpilot_app` (BYPASSRLS **yok**) |
| `SUPABASE_URL` | ✅ | JWKS/issuer bundan türetilir |
| `APP_DEBUG` | — | staging/production'da `true` **reddedilir** (§6) |
| `API_TRUSTED_HOSTS` | ✅ | Host allowlist'i; strict ortamda zorunlu, bare `*` yasak (bkz. [http-security.md](http-security.md)) |
| `APP_PORT`, `LOG_LEVEL`, `FRONTEND_BASE_URL` | — | Davet linki için `FRONTEND_BASE_URL` önerilir |

### Worker (runtime)

| Değişken | Zorunlu | Not |
|---|---|---|
| `APP_ENVIRONMENT` | ✅ | API ile aynı strict doğrulama |
| `DATABASE_URL` | ✅ | Uygulama rolü `flowpilot_app` (BYPASSRLS **yok**) |
| `WORKER_TENANT_IDS` | ✅ | Virgülle ayrılmış tenant UUID allowlist'i; boşsa süreç başlamaz |
| `WORKER_POLL_INTERVAL_SECONDS` | — | Sweep'ler arası bekleme; default `1.0`, minimum `0.1` |
| `WORKER_HEARTBEAT_PATH` | — | Default `/tmp/flowpilot-worker-heartbeat.json`; heartbeat **kapatılamaz**, boş değer reddedilir |
| `WORKER_HEARTBEAT_MAX_AGE_SECONDS` | — | Tazelik eşiği; default `60`, minimum `1.0`. Poll interval + en uzun sweep'ten **büyük** seçilir |

Worker'ın liveness'i HTTP ile ölçülemez (port yok). Bunun yerine süreç yaşam döngüsünü
heartbeat **JSON belgesine** yazar: startup'ta `starting`, her tamamlanan sweep'te tam
başarıysa `healthy` / en az bir tenant hatalıysa `degraded`, stop'ta `stopping` → `stopped`.
Container healthcheck'i `python -m flowpilot.worker --check-heartbeat` yalnız
`status=healthy` VE `last_full_success_at` eşik içinde tazeyse 0 döner — worker loop
başlatmaz ve **database'e dokunmaz**. Sürekli başarısız bir worker dosyayı taze yazsa bile
healthy sayılmaz. Belge yalnız status/pid/UTC damgaları/tenant SAYISI/hata sayacı içerir
(tenant UUID, DSN, secret, PII yok) ve kalıcı volume gerektirmez. Startup heartbeat'i
yazılamazsa worker fail-fast eder; sonraki yazım hataları loglanır ama **dispatch durmaz**
(dosya bayatlar, healthcheck düşer). Ayrıntılı yaşam döngüsü, checker kuralları ve operasyon
prosedürleri: [worker-operations.md](worker-operations.md).

### Web (runtime)

| Değişken | Zorunlu | Not |
|---|---|---|
| `FLOWPILOT_API_BASE_URL` | ✅ | **SERVER-ONLY** — `NEXT_PUBLIC_` öneki yoktur, browser bundle'a girmez |
| `PORT`, `HOSTNAME` | — | Default `3000` / `0.0.0.0` |

### Web (build-time — §2)

`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_APP_URL`.

> Service role key ve JWT secret **hiçbir katmanda yoktur** (ADR-005). Image'lara `.env`,
> `.pem`, `.key` **kopyalanmaz** (`.dockerignore`).

## 5. Migration release step

Migration **uygulama startup'ında ÇALIŞTIRILMAZ**. Ayrı, tek seferlik bir release adımıdır ve
API/Web başlatılmadan **önce** koşar. Başarısız olursa **deployment durur** (exit code > 0).

```bash
python scripts/run_production_migrations.py
```

- **Çalışma dizini:** repo kökü (veya `--alembic-ini` ile yol verilir)
- **Alembic config:** `apps/backend/alembic.ini` (script_location: `migrations/`)
- **Komut karşılığı:** `alembic -c apps/backend/alembic.ini upgrade head`
- **Bağlantı:** `MIGRATION_DATABASE_URL` → migrator rolü `flowpilot_migrator` (DDL yetkili,
  uygulama rolünden **ayrı**)
- `--check-only` bekleyen migration'ı raporlar, **upgrade çalıştırmaz**
- Script secret **yazdırmaz**, database **sıfırlamaz**, seed **çalıştırmaz**, downgrade **yapmaz**

Aynı API image'ı bu adım için de kullanılabilir (`alembic.ini` + `migrations/` image içindedir);
bu durumda container'a yalnız `MIGRATION_DATABASE_URL` verilir.

## 6. Production yapılandırma fail-fast

- **API:** `staging`/`production`'da `SUPABASE_URL` veya `DATABASE_URL` eksikse **başlamaz**;
  `APP_DEBUG=true` **reddedilir**; `production`'da `localhost`/`127.0.0.1` adresli
  `DATABASE_URL`/`SUPABASE_URL` **reddedilir**. Hata mesajları yalnız **değişken adı** içerir.
- **Web:** production runtime'da `FLOWPILOT_API_BASE_URL` / `NEXT_PUBLIC_APP_URL` eksikse
  localhost'a **sessizce düşmez**, anlaşılır hata verir; Supabase public değişkenleri eksikse
  fail-fast eder (çözüm: §2 build argümanlarıyla yeniden build).

## 7. API ↔ Frontend bağlantısı

Tarayıcı FastAPI'yi **doğrudan çağırmaz**. Next.js **server** tarafı `FLOWPILOT_API_BASE_URL`
ile FastAPI'ye Bearer istek yapar (`apps/web/src/lib/api/http.ts` → `import "server-only"`).
Bu nedenle API'nin public internete açılması **zorunlu değildir**; sağlayıcı private
networking sunuyorsa API private tutulabilir.

## 8. Sağlayıcı kurulumunda yapılacaklar (bu dilimin dışında)

- **Supabase redirect/allow-list**: Site URL + `/auth/callback` (staging + production) sağlayıcı
  ve Supabase panelinde yapılandırılır — repository'de saklanmaz.
- **Persistent database**: PostgreSQL **container içinde tutulmaz**; managed servis kullanılır
  (yedek/PITR sağlayıcı tarafında yapılandırılır).
- **Object storage**: Mevcut pilot kapsamı için **zorunlu değildir** — dosya eki özelliği ve
  `FileStoragePort` adapter'ı yoktur. `infra/containers/compose.yaml` içindeki MinIO yalnız
  **local development** içindir.
- **TLS / domain / reverse proxy**: sağlayıcı katmanında.

## 9. Bu dilimde bilinçli olarak YOK

| Konu | Nereye ait |
|---|---|
| Worker otomatik ölçekleme / birden çok replika koordinasyonu | Sağlayıcı katmanı (outbox `FOR UPDATE SKIP LOCKED` çoklu worker'a hazırdır) |
| Readiness'in container healthcheck'i olarak kullanılması | Bilinçli DEĞİL: geçici database kesintisi sağlıklı API sürecini öldürmemeli; readiness platform trafik kararına aittir |
| Güvenlik header'ları, CORS, rate limiting | **FP-OPS-003** |
| Hata izleme, e-posta, metrik | FP-OPS-004 ve sonrası |
| Sağlayıcı seçimi / manifest | ADR-010 kapsamı — **değiştirilmedi** |
