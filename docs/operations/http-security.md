# FlowPilot — Backend HTTP Security (Provider-Neutral)

> **Kapsam:** FP-OPS-003A. Bu belge yalnız **uygulanmış** sözleşmeleri anlatır:
> TrustedHost, staging/production docs/OpenAPI kapatma ve temel API response
> header'ları. CORS'un neden eklenmediği burada; HSTS/proxy/rate-limit/CSP bu
> dilimde **uygulanmamıştır** (bkz. §6). ADR-010 ve LOCK-006 değiştirilmemiştir.
>
> Tamamlayıcı belgeler: [container-deployment.md](container-deployment.md),
> [deployment-runbook.md](deployment-runbook.md), [worker-operations.md](worker-operations.md).

## 1. TrustedHost

Backend, Starlette `TrustedHostMiddleware` ile Host header'ını doğrular.
Yapılandırma **`API_TRUSTED_HOSTS`** environment değişkenindendir (secret değildir).

**Parsing (deterministik):** virgülle bölünür → whitespace temizlenir → boş
öğeler atılır → lowercase normalize edilir → duplicate'ler **ilk görülme**
sırası korunarak kaldırılır. `*.example.com` biçimindeki alt-domain wildcard'ı
desteklenir. Karşılaştırma port'suzdur (`api.example.com:8000` → `api.example.com`).

**Ortam davranışı:**

| Ortam | Unset/boş | Dolu |
|---|---|---|
| local / test / development | Middleware **eklenmez** (mevcut davranış korunur) | Allowlist uygulanır (izinsiz host → 400) |
| staging / production | **Startup fail-fast** (hata yalnız `API_TRUSTED_HOSTS` adını söyler; host listesi/değer yazılmaz) | Allowlist uygulanır |

- Bare `*` staging/production'da **reddedilir** (startup fail-fast).
- İzinsiz Host → **HTTP 400**; izinli Host normal yanıt alır.

**Healthcheck implicit host'ları:** strict ortamlarda `localhost`, `127.0.0.1`
ve `::1` allowlist'e **dahili olarak** eklenir — container healthcheck'i
(`http://127.0.0.1:<port>/health/live`) hiçbir yapılandırmayla kırılmaz.
Managed provider'ın internal probe hostname'i **tahmin edilmez**; platform
farklı bir Host ile probe yapıyorsa o ad `API_TRUSTED_HOSTS` içine açıkça eklenir.

**Bilinen sınır (IPv6):** Starlette, Host'u naif `split(":")` ile ayırdığı için
köşeli parantezli IPv6 literal'i (`[::1]:8000`) hiçbir kalıpla eşleşmez ve
**fail-closed 400** alır. Container healthcheck IPv4 kullandığından etkilenmez.

## 2. Staging/production'da docs/OpenAPI kapalı

| Yol | local/test/development | staging/production |
|---|---|---|
| `/docs` | 200 | **404** |
| `/redoc` | 200 | **404** |
| `/openapi.json` | 200 | **404** |

Açma flag'i **bilinçli olarak yoktur**: API sözleşmesi repository'dedir ve
OpenAPI koddan offline üretilebilir. Production'da docs açma istisnası bu
dilimin dışındadır.

## 3. Temel API response header'ları

Her HTTP yanıtına (başarı, health, 404, TrustedHost 400, 422, handled hatalar)
saf ASGI middleware ([security_headers.py](../../apps/backend/src/flowpilot/api/security_headers.py))
şu header'ları ekler — **yalnız yanıtta zaten yoksa** (duplicate üretilmez;
endpoint'in açıkça koyduğu değer korunur):

| Header | Değer | Neden |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | MIME sniffing engellenir |
| `Referrer-Policy` | `no-referrer` | Referrer sızıntısı yok |
| `Cache-Control` | `no-store` | API yanıtları Confidential sınıfıdır; cache'lenmez |

Body/status değiştirilmez; streaming bozulmaz (header'lar `http.response.start`
mesajına eklenir).

**Bilinen sınır (unhandled 500):** Starlette'in en dıştaki `ServerErrorMiddleware`'i
unhandled exception 500 yanıtını bu middleware devreye girmeden üretir; o yanıt
bu header'ları taşımaz (gövdesi jenerik `Internal Server Error`'dır, detay
sızdırmaz). Generic 500 handler bu dilimde bilinçli olarak eklenmemiştir.

**Middleware sırası:** SecurityHeaders **en dışta**, TrustedHost içinde —
TrustedHost'un 400 yanıtı da header'ları taşır.

## 4. CORS bilinçli olarak yok

`CORSMiddleware` **eklenmemiştir** ve hiçbir yanıt `Access-Control-Allow-Origin`
taşımaz. Gerekçe (kanıta dayalı):

- Browser FastAPI'ye **doğrudan istek atmaz**: tüm API çağrıları Next.js'in
  server-only katmanından yapılır (`FLOWPILOT_API_BASE_URL` `NEXT_PUBLIC_`
  öneksizdir; `apps/web/src/lib/api/http.ts` `server-only` import'ludur).
- Next.js server-to-server istekleri CORS'a tabi değildir; CORS'suz production
  akışı tam çalışır.
- Public API / üçüncü taraf entegrasyon MVP kapsamında değildir. O gün gelirse
  açık origin allowlist'iyle ayrı bir story açılır.

CORS'un yokluğu en güvenli durumdur; permissive CORS eklemek duruşu zayıflatır.
Bu sözleşme contract testiyle korunur (`test_no_cors_headers_on_any_response`).

## 5. Debug ve proxy sınırı (değişmedi)

- `APP_DEBUG=true` staging/production'da reddedilmeye devam eder (FP-OPS-001).
- Production image reload kullanmaz; Uvicorn CMD bu dilimde **değiştirilmedi**
  (`--proxy-headers` / `--forwarded-allow-ips` eklenmedi).
- Uygulama `request.client` veya `X-Forwarded-*` temelli hiçbir güvenlik kararı
  vermez; davet linki canonical `FRONTEND_BASE_URL`'den üretilir.

## 6. Bu dilimde bilinçli olarak uygulanmayanlar

| Konu | Neden / nereye ait |
|---|---|
| HSTS | TLS termination edge'dedir; sağlayıcı seçiminde edge katmanında yönetilir |
| CSP / X-Frame-Options / Permissions-Policy | HTML yüzeyine aittir → Next.js dilimi (FP-OPS-003B) ve ayrı CSP dilimi |
| Proxy trust (`--forwarded-allow-ips`) | Sağlayıcı seçimine bağlı; o güne dek IP tabanlı karar verilmez |
| Rate limiting | Katman/store kararı sağlayıcıya bağlı; ayrı tasarım dilimi |
| HTTPS redirect | Edge'de; uygulama katmanında healthcheck'i kırar |
