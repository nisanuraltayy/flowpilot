# FlowPilot — HTTP Security (Provider-Neutral)

> **Kapsam:** FP-OPS-003A (backend) + FP-OPS-003B (frontend). Bu belge yalnız
> **uygulanmış** sözleşmeleri anlatır: TrustedHost, staging/production docs/OpenAPI
> kapatma, temel API response header'ları ve Next.js baseline security header'ları. CORS'un neden
> eklenmediği burada; HSTS/proxy/rate-limit/CSP **uygulanmamıştır** (bkz. §7). ADR-010 ve LOCK-006 değiştirilmemiştir.
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

Kesin kurallar:

- Browser yalnız Next.js uygulaması ve Supabase auth yüzeyiyle konuşur.
- `Access-Control-Allow-Origin: *` **yasaktır**.
- Credential'lı wildcard CORS **hiçbir zaman** kabul edilmez.
- Gelecekte browser'ın FastAPI'ye doğrudan erişmesi gerekirse **ayrı story** açılır
  ve o story şunları içermek zorundadır: explicit origin allowlist, credentials
  davranışı kararı, preflight (OPTIONS) davranışı ve cache/`Vary: Origin` testleri.

CORS "unutulmuş" değildir; **bilinçli olarak uygulanmamıştır**.

## 5. Debug, proxy ve forwarded-header trust

- `APP_DEBUG=true` staging/production'da reddedilmeye devam eder (FP-OPS-001).
- Production image reload kullanmaz; Uvicorn CMD **değiştirilmedi**
  (`--proxy-headers` / `--forwarded-allow-ips` eklenmedi — FP-OPS-003C dahil).

**Mevcut durum (kanıtlı):** Uvicorn startup sözleşmesi explicit trusted-proxy
CIDR **pinlemez**. Uygulama `request.client`, forwarded scheme veya forwarded
host bilgisini **hiçbir auth/authorization kararında kullanmaz**; canonical davet
ve frontend URL'leri `FRONTEND_BASE_URL`'den üretilir. Bu nedenle bugünkü
güvenlik etkisi sınırlıdır; ancak loglanan client IP / scheme bilgisi
deployment'a göre **güvenilir olmayabilir**.

**Kesin kurallar (sağlayıcı seçilene kadar):**

- `X-Forwarded-For` / `X-Forwarded-Host` / `X-Forwarded-Proto` **hiçbir güvenlik
  kararında kullanılamaz**.
- IP tabanlı rate limit **uygulanamaz**.
- Client IP, audit kanıtı olarak **tek başına kabul edilemez**.
- Arbitrary `--forwarded-allow-ips=*` **eklenemez**.
- Trusted proxy aralığı yalnız seçilen sağlayıcının **belgelenmiş** egress/proxy
  CIDR'ına veya socket sınırına göre pinlenir; bu, production deployment
  sözleşmesinin parçasıdır ve provider seçildiğinde Docker/start command veya
  platform config **ayrı değişiklik** olarak ele alınır (bkz. OQ-011).

## 6. Next.js baseline security header'ları (FP-OPS-003B)

`apps/web/next.config.ts` içindeki `headers()` catch-all kaynakla (`/(.*)`) —
sayfalar, route handler'lar ve `_next/static` asset'leri dahil — **tüm**
yanıtlara şu beş header'ı ekler:

| Header | Değer | Neden |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Browser MIME sniffing kapalı |
| `X-Frame-Options` | `DENY` | Ürün kapsamında iframe/embed gereksinimi yok → framing tamamen engelli (clickjacking) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Cross-origin isteklere tam URL/path sızmaz; same-origin navigasyon bilgisi korunur |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Kullanılmayan güçlü browser yetenekleri kapalı |
| `Cross-Origin-Opener-Policy` | `same-origin` | Browsing-context izolasyonu; repo'da popup tabanlı OAuth / `window.open` akışı **yoktur** (doğrulandı) |

Kurallar ve doğrulanan davranış:

- Header'lar **duplicate değildir** (contract testi + runtime smoke ile pinli).
- Route body, redirect ve status davranışı **değişmez**: login/signup/invitation
  akışları, korumalı-yol → login yönlendirmesi ve open-redirect koruması aynen
  çalışır (mevcut testler + standalone runtime smoke).
- `output: "standalone"` korunur; `poweredByHeader` bu dilimde değiştirilmemiştir.
- **CSP bu dilimde bilinçli olarak yoktur**: App Router hydration inline
  script'leri nonce tabanlı dinamik CSP ister; statik config CSP'si production
  build'i kırma riski taşır ve `connect-src` deployment'a göre değişen Supabase
  URL'sine bağlıdır → ayrı, doğrulanmış CSP dilimi.
- **HSTS** TLS termination/edge kararına bırakılmıştır (backend ile aynı gerekçe).
- **CORS** eklenmemiştir: backend'e trafik server-only'dir (§4).
- İleride popup tabanlı OAuth, embed veya iframe gereksinimi eklenirse
  `Cross-Origin-Opener-Policy` ve `X-Frame-Options` sözleşmesi **yeniden incelenir**.

## 6b. Next.js Content Security Policy (FP-OPS-004A)

Nonce tabanlı CSP **enforce** edilir (Report-Only YOK; violation reporting servisi
bilinçli olarak kurulmamıştır). Politika `apps/web/src/lib/csp.ts`'te deterministik
üretilir; `src/proxy.ts` her document isteği için **yeni 128-bit Web Crypto nonce**
üretip politikayı hem request header'ına (Next render katmanı framework inline
script'lerine nonce'ı buradan uygular) hem response'a yazar. Nonce loglanmaz,
cookie'ye/başka header'a yazılmaz.

**Production politikası:** `default-src 'none'` · `base-uri 'self'` ·
`object-src 'none'` · `frame-ancestors 'none'` (X-Frame-Options: DENY ile uyumlu) ·
`form-action 'self'` · `script-src 'self' 'nonce-…' 'strict-dynamic'` ·
`style-src/img-src/font-src/connect-src 'self'` · `worker-src/frame-src 'none'`.
`unsafe-eval`/`unsafe-inline`/`data:`/`blob:`/`wss:` ve **hiçbir dış origin yoktur** —
browser Supabase'e doğrudan bağlanmaz (tüm auth server-side; kanıt: FP-OPS-004
audit). **Development farkı yalnız HMR içindir:** script-src `'unsafe-eval'`,
style-src `'unsafe-inline'`, connect-src `ws:` — production'a sızmadığı testle pinlidir.

**Dynamic rendering etkisi (owner-onaylı):** daha önce prerender edilen
`/signup`, `/auth/check-email`, `/auth/error`, `/onboarding/organization`
sayfaları `export const dynamic = "force-dynamic"` ile request-time render'a
alındı (build-time HTML nonce'suz kalırdı). Framework'ün `_not-found` /
`_global-error` sayfaları static kalır — 404 üzerindeki runtime CSP davranışı
FP-OPS-004B doğrulamasının konusudur. Baseline beş header `next.config.ts`'te
değişmeden durur; CSP **yalnız proxy katmanından** gelir. Yeni environment
değişkeni yoktur. Kapsamlı runtime/Docker/browser doğrulaması FP-OPS-004B'de
tamamlanacaktır.

## 7. Deferred controls and deployment-dependent decisions (FP-OPS-003C)

Bu bölümdeki kontrollerin **hiçbiri uygulanmamıştır**; her biri *deferred*
(ertelenmiş) veya *requires provider decision* (sağlayıcı kararı gerektirir)
durumundadır. Bu görev (FP-OPS-003C) yalnız kararları kayıt altına alır — kod,
dependency veya runtime davranışı değiştirilmemiştir.

### 7.1 Rate limiting — deferred (tasarım kaydı)

**Neden şimdi uygulanmıyor:**

- Güvenilir client IP henüz yoktur (trusted proxy pinlenmedi — §5).
- Multi-container ortamda process-local/in-memory limiter **tutarsızdır**;
  in-memory limiter production sözleşmesi olarak kabul edilmez.
- Redis veya başka paylaşımlı limiter store mevcut stack'te yoktur; yeni
  dependency ve operasyon yükü mimari karar gerektirir (bkz. OQ-012).
- Public davet token'ları yüksek entropili CSPRNG token'larıdır
  (`secrets.token_urlsafe`); brute force pratik değildir.
- Diğer hassas endpoint'lerin tamamına yakını auth gerektirir; liste
  endpoint'leri bounded pagination kullanır.

**Hedef mimari (planned) — iki katman:**

1. **Edge/provider limiter:** hacimsel ve kaba IP tabanlı koruma, sağlayıcı
   üzerinde uygulanır. Health endpoint'leri muaf tutulur veya ayrı yüksek
   limite sahip olur.
2. **Application endpoint-specific limiter:** hassas iş akışları için,
   paylaşımlı store ile, multi-process/multi-container tutarlı.

**Endpoint öncelikleri (planned):**

| Politika | Endpoint'ler |
|---|---|
| Daha sıkı | Davet preview, davet accept, organization creation, davet create/revoke, approval decision/resolve mutation'ları |
| Daha genel | Purchase request creation, admin mutation'ları, authenticated read/list |
| Muaf / ayrı politika | `/health/live`, `/health/ready` (worker heartbeat checker HTTP endpoint değildir) |

**Anahtar stratejisi (planned):** auth'lu endpoint'lerde `tenant_id +
authenticated user_id` (gerekirse + endpoint/action adı); public endpoint'lerde
trusted proxy kararı tamamlandıktan sonra client IP, gerekirse token
fingerprint — **raw token asla loglanmaz ve store key'ine yazılmaz**.

**Response sözleşmesi (planned):** HTTP **429** + `Retry-After` header +
generic/sanitize edilmiş gövde; secret/token/IP dump yok.

**Store — açık karar (OQ-012):** Redis vs provider-native distributed limiter.
Mevcut PostgreSQL'in limiter store olarak kullanılması tercih edilmemektedir
(operasyonel tabloların hot-path yüküyle karışmaması ilkesi); nihai karar
store değerlendirmesiyle birlikte verilir.

### 7.2 Request body ve timeout sınırları — deferred

**Mevcut durum:** upload endpoint'i yok; JSON modellerinde Pydantic alan
sınırları var; frontend API timeout'u 10 sn; JWKS timeout'u 5 sn;
application-level **global request-body byte limiti yok**; DB
`statement_timeout` / `lock_timeout` application config'inde yok.

**Karar:** request-body byte limiti **edge/provider katmanında** açıkça
ayarlanır ve provider seçildiğinde maksimum body size deployment checklist'ine
eklenir (OQ-013). Gelecekte upload özelliği eklenirse endpoint-specific
size/type validation **zorunludur**. DB `statement_timeout`/`lock_timeout`
ayrı bir database provisioning/hardening story'sidir. Bu alanların hiçbiri
FP-OPS-003C'de uygulanmamıştır; kodda olmayan limit değeri bu belgeye yazılmaz.

### 7.3 Diğer ertelenmiş kontroller

| Konu | Durum | Neden / nereye ait |
|---|---|---|
| HSTS | Requires provider decision (OQ-014) | TLS termination edge'dedir (§3 ve §6'daki gerekçe) |
| CSP violation reporting | Deferred | Collector/telemetry kurulmadan Report-Only değersiz; sağlayıcı sonrası değerlendirilir (CSP kendisi UYGULANDI — §6b) |
| Proxy trust (`--forwarded-allow-ips`) | Requires provider decision (OQ-011) | §5'teki kesin kurallar geçerli |
| HTTPS redirect | Edge'de | Uygulama katmanında healthcheck'i kırar |
| Edge WAF | Requires provider decision | Sağlayıcı yeteneklerine bağlı |
