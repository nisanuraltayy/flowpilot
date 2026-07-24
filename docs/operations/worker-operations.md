# FlowPilot — Worker Operations (Provider-Neutral)

> **Kapsam:** FP-OPS-002. Worker servis modunun (`--serve`) çalıştırılması, izlenmesi ve
> sorun giderilmesi. Bu belge **sağlayıcı seçmez** ve
> [ADR-010](../adr/ADR-010-initial-hosting-and-data-region.md) / LOCK-006 kararlarını
> **değiştirmez**; her prosedür container çalıştırabilen herhangi bir platformda geçerlidir.
>
> Tamamlayıcı belgeler: [container-deployment.md](container-deployment.md) (image build/run
> sözleşmesi), [deployment-runbook.md](deployment-runbook.md) (ortamlar, migration, rollback).

## 1. API health endpoint'leri

Worker'ın sağlığı API'den **bağımsız** izlenir; yine de operasyon sırasında ikisi birlikte
okunur:

| Endpoint | Ne kontrol eder | Sonuç |
|---|---|---|
| `GET /health/live` | Yalnız process ayakta mı — **hiçbir dış bağımlılık kontrol edilmez** | Her zaman 200 `{"status":"ok"}`; database kapalıyken bile 200 dönebilir |
| `GET /health/ready` | Uygulamanın **paylaşılan (cache'lenmiş) SQLAlchemy session factory'si** ile database'e `SELECT 1` | Başarıda 200 `{"status":"ready","checks":{"database":{"status":"ok"}}}`; başarısızlıkta 503 `{"status":"not_ready","checks":{"database":{"status":"failed"}}}` |

Readiness kuralları:

- Her istekte **yeni engine kurulmaz**; paylaşılan session factory yeniden kullanılır.
- Hata durumunda **raw exception, DSN, host, kullanıcı adı, parola veya stack trace
  response'a taşınmaz** — yalnız `failed` döner.
- Readiness **Supabase, worker heartbeat veya object storage kontrol etmez**; kapsamı yalnız
  database bağlantısıdır.
- Her iki endpoint de authentication **gerektirmez** ve 401/403 dönmez.

## 2. Worker image build ve start

```bash
docker build --target worker-runtime -t flowpilot-worker:local apps/backend
```

`--target` verilmeden yapılan build **API image'ı üretmeye devam eder** (Dockerfile'daki son
stage `api`'dir; worker hiçbir koşulda default process değildir):

```bash
docker build -t flowpilot-api:local apps/backend
```

Worker container'ının default komutu:

```bash
python -m flowpilot.worker --serve
```

- HTTP portu **dinlemez**; API'nin `/health/live` healthcheck'i worker'da kullanılmaz.
- Non-root çalışır (uid `10001`), startup'ta **migration çalıştırmaz**, uvicorn başlatmaz.

## 3. Tenant allowlist

Worker **global tenant discovery YAPMAZ** ve **RLS bypass kullanmaz**: uygulama rolü
`flowpilot_app` NOBYPASSRLS'tir ve her tenant kendi RLS context'inde işlenir. Bu yüzden
işlenecek tenant'lar **açıkça** verilir:

- CLI: `--tenant <uuid>` (tekrarlanabilir), veya
- Environment: `WORKER_TENANT_IDS=<uuid[,uuid...]>` (virgülle ayrılmış)

Kurallar:

- **CLI verilmişse yalnız CLI geçerlidir** — iki kaynak asla birleştirilmez.
- Duplicate UUID'ler **ilk görülme sırası korunarak** kaldırılır.
- Hiç tenant yoksa süreç **kontrollü hata** ile çıkar; sessizce boş çalışmaz.
- Geçersiz UUID kontrollü hata üretir.

## 4. Worker environment değişkenleri (yalnız ADLAR — gerçek değer yazılmaz)

| Değişken | Zorunlu | Default | Secret? | Doğrulama / öncelik |
|---|---|---|---|---|
| `DATABASE_URL` | ✅ | — | ✅ (bağlantı dizesi parola içerir) | `flowpilot_app` rolü (BYPASSRLS yok); secret manager'dan enjekte edilir |
| `WORKER_TENANT_IDS` | ✅ (CLI `--tenant` verilmediyse) | — | Hayır (tenant UUID'leri secret değildir ama bu belgeye/gerçek örneklere yazılmaz) | Virgülle ayrılmış geçerli UUID listesi; CLI `--tenant` **önceliklidir**, kaynaklar birleştirilmez |
| `WORKER_POLL_INTERVAL_SECONDS` | — | `1.0` | Hayır | Minimum `0.1`; `0`, negatif, `0.1` altı, NaN, infinity ve sayısal olmayan değer reddedilir. CLI `--interval` **önceliklidir** |
| `WORKER_HEARTBEAT_PATH` | — | `/tmp/flowpilot-worker-heartbeat.json` | Hayır | Heartbeat **kapatılamaz**: değişken tanımsızsa default kullanılır; tanımlı ama boş/whitespace değer **reddedilir** |
| `WORKER_HEARTBEAT_MAX_AGE_SECONDS` | — | `60.0` | Hayır | Minimum `1.0` (`1.0` kabul edilir); `0`, negatif, `1` altı, NaN, infinity ve sayısal olmayan değer reddedilir. Poll interval + en uzun sweep süresinden **büyük** seçilir |
| `APP_ENVIRONMENT` | ✅ | `local` | Hayır | API ile aynı strict production doğrulaması |

Hata mesajları yalnız **değişken adını ve hata kategorisini** söyler; ham değer veya başka
environment içeriği yazdırılmaz.

## 5. Polling ve fairness

- Her sweep'te tenant'lar **ilk görülme sırasıyla** işlenir; sıra **her sweep'te aynıdır**
  (rotasyon yoktur, sıra deterministiktir).
- Her tenant sweep başına **tam bir dispatch pass** ve aynı `--limit` değerini alır — yoğun
  bir tenant diğerlerini **aç bırakamaz**.
- Bir tenant'ın pass'i hata verirse yalnız hata **tipi** loglanır ve döngü **diğer
  tenant'larla devam eder**; başarısız tenant **sonraki sweep'te aynı konumunda** yeniden
  denenir (aynı sweep içinde tekrar denenmez).
- Sweep tamamlanınca heartbeat güncellenir ve `--interval` (yoksa
  `WORKER_POLL_INTERVAL_SECONDS`, o da yoksa default) kadar beklenir; bekleme
  SIGTERM/SIGINT ile kesilebilir. Busy-spin engellenmiştir.

## 6. Heartbeat yaşam döngüsü

Worker, yaşam döngüsünü default olarak `/tmp/flowpilot-worker-heartbeat.json` yoluna
**atomik JSON belgesi** olarak yazar (aynı dizinde geçici dosya → UTF-8 JSON → flush →
fsync → `os.replace`; POSIX'te dosya izni `0600`). Yarım/bozuk JSON asla görünmez ve kalıcı
volume gerekmez.

Belge alanları: `status`, `pid`, `started_at`, `updated_at`, `last_full_success_at`,
`tenant_count`, `consecutive_failed_sweeps`. Timestamp'ler UTC ve `Z` soneklidir.
**Tenant UUID, tenant listesi, DSN, token, e-posta, raw exception, traceback veya
environment içeriği dosyaya asla yazılmaz** — tenant bilgisi yalnız **sayı** olarak bulunur.

Status geçişleri:

| Status | Ne zaman |
|---|---|
| `starting` | Runtime wiring kurulduktan sonra, ilk sweep'ten **önce**. **Sağlıklı sayılmaz** |
| `healthy` | Bir sweep'te **bütün** tenant pass'leri başarılıysa. `last_full_success_at` güncellenir, `consecutive_failed_sweeps` sıfırlanır |
| `degraded` | Sweep'te **en az bir** tenant hata verdiyse. `last_full_success_at` **ilerlemez** (önceki değerinde kalır), `consecutive_failed_sweeps` artar |
| `stopping` | Stop talebi işlendi; yeni tenant/sweep başlatılmayacak |
| `stopped` | Runtime dispose tamamlandı |

Ek kurallar:

- Sonraki tam başarı sayaç değerini **sıfırlar** ve `last_full_success_at`'i günceller.
- Startup heartbeat'i yazılamazsa worker **fail-fast** eder (loop hiç başlamaz, wiring
  dispose edilir, exit 1).
- Çalışma sırasındaki yazım hatası loglanır ama **dispatch'i durdurmaz** ve busy-retry
  yapılmaz — dosya bayatlar, healthcheck doğal olarak düşer.

## 7. Container healthcheck

```bash
python -m flowpilot.worker --check-heartbeat
```

Checker **database bağlantısı kurmaz**, runtime wiring oluşturmaz, worker loop başlatmaz ve
heartbeat dosyasına **yazmaz** — yalnız okur ve doğrular.

Exit `0` yalnız **tüm** koşullar sağlanınca:

- Dosya mevcut, okunabilir ve kökü JSON object olan geçerli JSON
- `status == "healthy"`
- `last_full_success_at` mevcut, geçerli ve timezone-aware
- Damga bayat değil (`now - last_full_success_at <= WORKER_HEARTBEAT_MAX_AGE_SECONDS`)
- Damga en fazla 5 saniye gelecekte (saat kayması toleransı)
- Alan tipleri geçerli (`pid` pozitif integer, `tenant_count` sayı, sayaç ≥ 0 integer,
  diğer timestamp'ler geçerli)

Unhealthy (non-zero) durumlar: eksik/okunamayan/bozuk dosya · `starting` / `degraded` /
`stopping` / `stopped` / bilinmeyen status · eksik `last_full_success_at` · bayat, naive
veya 5 saniyeden fazla gelecekteki damga · geçersiz alan tipleri · geçersiz yapılandırma.

> `updated_at` tazeliği **tek başına yeterli değildir**: sürekli başarısız bir worker
> dosyayı taze yazmaya devam eder ama `degraded` kaldığı için healthy sayılmaz.

## 8. Graceful shutdown

- `SIGTERM` ve `SIGINT` yakalanır.
- Devam eden tenant pass'i **tamamlanır** (transaction zorla kesilmez); yeni tenant veya
  sweep **başlatılmaz**.
- Stop işlenince heartbeat'e `stopping` yazılır → runtime **dispose** edilir → `stopped`
  yazılır (her ikisi best-effort; business invariant heartbeat'e bağlanmaz).
- Normal kapanış exit code `0` ile biter.

## 9. Operasyon prosedürleri

### 9.1 Yeni organization eklendiğinde

1. Yeni tenant'ın UUID'sini worker'ın allowlist'ine ekle (`WORKER_TENANT_IDS` değerine
   virgülle, veya CLI `--tenant` listesine).
2. Worker'ı güvenli biçimde yeniden başlat (bkz. §9.3) — allowlist yalnız startup'ta okunur.
3. Heartbeat `healthy` olana kadar kontrol et (`--check-heartbeat` exit 0 ve
   `tenant_count` yeni sayıyı gösterir).

### 9.2 Worker unhealthy ise (tanı sırası)

1. **Container/process durumu:** süreç ayakta mı, restart döngüsünde mi?
2. **Heartbeat status:** `starting` (henüz ilk tam başarı yok) / `degraded` (tenant
   hataları) / `stopping`-`stopped` (kapanmış) ayrımını yap.
3. **`last_full_success_at` tazeliği:** en son ne zaman tam başarılı sweep oldu?
4. **`consecutive_failed_sweeps`:** artıyorsa hata süreklidir, tek seferlik değildir.
5. **Database erişimi:** API `/health/ready` 503 dönüyorsa sorun büyük olasılıkla
   database'dir, worker'a özgü değildir.
6. **Allowlist formatı:** `WORKER_TENANT_IDS` geçerli, virgülle ayrılmış UUID listesi mi?
   (Boş liste veya bozuk UUID startup'ta kontrollü hata üretir.)
7. **Sanitized worker logları:** `worker.tenant_failed` (hata tipi + tenant),
   `worker.heartbeat_write_failed` kayıtlarına bak — loglar secret içermez.

### 9.3 Worker restart

1. Sürece `SIGTERM` gönder (container platformunda stop komutu).
2. Sürecin `stopped` heartbeat'i yazıp exit 0 ile kapandığını bekle.
3. Yeni süreci başlat.
4. İlk tam başarılı sweep sonrası `--check-heartbeat` exit 0 olduğunu doğrula
   (`starting` durumu healthcheck'te sağlıksızdır; start-period toleransı bunun içindir).

### 9.4 Worker çalışmazsa etkisi

- Timer'a bağlı işlemler **gecikir** (timer'lar veritabanında kalıcıdır, kaybolmaz).
- Outbox backlog'u **büyür**; event'ler veritabanında bekler, kaybolmaz.
- Ana request-time akışlar (ör. purchase request onay/ret kararının API üzerinden verilmesi)
  **çalışmaya devam edebilir** — karar, state + outbox + audit'i aynı transaction'da yazar.
- Worker geri döndüğünde backlog, mevcut **lease + bounded retry** kurallarıyla işlenir
  (`FOR UPDATE SKIP LOCKED`; sonsuz retry yoktur). "Exactly once" iddiası yoktur;
  at-least-once + idempotent consumer geçerlidir.

### 9.5 Migration

- Worker startup'ta **migration çalıştırmaz** (API da çalıştırmaz).
- Migration ayrı release adımıdır: bkz.
  [container-deployment.md §5](container-deployment.md) ve
  `scripts/run_production_migrations.py`.

### 9.6 Hosting

- Gerçek hosting sağlayıcısında deployment henüz **yapılmamıştır**; ilk hedef ADR-010'da
  kayıtlıdır ve bu belge onu **değiştirmez**.
- Buradaki her prosedür provider-neutral'dır: container çalıştırabilen, environment
  variable enjekte edebilen ve SIGTERM ile durdurabilen her platformda aynıdır.
