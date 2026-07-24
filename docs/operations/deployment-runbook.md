# FlowPilot Deployment Runbook (Provider-Neutral)

> **Kapsam.** Bu runbook FlowPilot MVP v0.1.0'ı bir ortama nasıl güvenle taşıyacağını
> tarif eder. **Provider-neutral**'dir (uygulama kodu sağlayıcıya bağlı değildir). İlk
> hosting kararı verildi: **Render (Frankfurt)** (ADR-010; LOCK-006 kapandı) — sağlayıcıya
> özgü kurulum [render-staging-plan.md](render-staging-plan.md)'dedir. Bu belge **gerçek bir
> deployment yapıldığını iddia ETMEZ**; hazırlık ve prosedürdür.
>
> **Güvenlik:** Bu belgede hiçbir gerçek secret, token, parola veya örnek gerçek değer
> bulunmaz — yalnız değişken **adları** ve açıklamaları.

## 1. Bileşenler

| Bileşen | Ne | Notlar |
|---|---|---|
| **Web** | Next.js 16 (App Router) | SSR + server actions; Bearer token yalnız server-side; browser'dan FastAPI'ye doğrudan çağrı yok |
| **Backend API** | FastAPI (`flowpilot.api.main:app`) | uvicorn/ASGI; `flowpilot_app` (NOBYPASSRLS) DB rolüyle bağlanır |
| **Worker** | `flowpilot.worker` | Outbox polling dispatcher; ayrı process (web ile aynı distribution) |
| **PostgreSQL** | Operasyonel tek source of truth | RLS ENABLE+FORCE; app rolü BYPASSRLS'siz |
| **Object storage** | S3-compatible (local: MinIO) | MVP akışında kullanılmıyor; `FileStoragePort` hazır |
| **Auth** | Supabase Auth | Yalnız authentication (ADR-005); token doğrulama backend'de (JWKS) |

## 2. Ortamlar

| Ortam | Amaç | `APP_ENVIRONMENT` |
|---|---|---|
| **local** | Geliştirme (Docker Compose Postgres + MinIO) | `local` |
| **staging** | Production-benzeri doğrulama; canlı acceptance checklist burada koşar | `staging` |
| **production** | Pilot/gerçek kullanım | `production` |

`staging`/`production`'da eksik zorunlu yapılandırma (SUPABASE_URL, DATABASE_URL)
uygulamayı **başlangıçta açık hata ile durdurur** (sessiz kabul edilmez).

## 3. Environment variable envanteri (yalnız ADLAR)

> Değerler **asla** bu belgeye veya repository'ye yazılmaz. Her ortam kendi secret
> manager'ından enjekte eder. `.env` / `.env.local` commit edilmez.

**Backend:**

| Değişken | Açıklama |
|---|---|
| `APP_ENVIRONMENT` | `local` / `staging` / `production` |
| `DATABASE_URL` | `flowpilot_app` (NOBYPASSRLS) uygulama DML bağlantısı |
| `MIGRATION_DATABASE_URL` | `flowpilot_migrator` (DDL) — **yalnız migration adımında**, runtime'da değil |
| `SUPABASE_URL` | Token doğrulama (JWKS/issuer) için Supabase proje URL'i |
| `SUPABASE_JWT_AUDIENCE` | Beklenen audience claim'i |
| `SUPABASE_JWT_ALLOWED_ALGORITHMS` | İzinli imza algoritmaları (ör. ES256/RS256) |

**Frontend (Next.js):**

| Değişken | Görünürlük | Açıklama |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | public | Supabase proje URL'i |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | public | Publishable (anon) key — tarayıcıya gidebilen tek anahtar |
| `FLOWPILOT_API_BASE_URL` | **server-only** | FastAPI taban adresi (`NEXT_PUBLIC_` öneki YOK) |
| `NEXT_PUBLIC_APP_URL` | public | Auth callback URL'inin türetildiği public adres |

**YASAK env:** `SUPABASE_SERVICE_ROLE_KEY`, JWT secret veya herhangi bir Supabase gizli
anahtarı bu uygulamalarda kullanılmaz.

## 4. Build adımları

**Backend (container image önerilir; provider-neutral):**
1. Python 3.12/3.13 tabanı.
2. `pip install -e "apps/backend"` (runtime bağımlılıkları; dev extras production image'a girmez).
3. Entrypoint(ler): API → `uvicorn flowpilot.api.main:app`; worker →
   `python -m flowpilot.worker --serve` (tenant allowlist zorunlu; bkz.
   [worker-operations.md](worker-operations.md)).

**Frontend:**
1. Node 20 LTS.
2. `npm ci` (apps/web).
3. `npm run build` → `.next` production çıktısı; `npm run start` ile sunulur.

CI hepsini otomatik doğrular (bkz. `.github/workflows/ci.yml`).

## 5. Database migration stratejisi (expand-only)

**Sıra: Backup → Expand → Deploy → Verify → (gerekirse) Contract.**

1. **Backup** — deploy öncesi tam DB yedeği ZORUNLU (bkz. §11). Yedek doğrulanmadan devam edilmez.
2. **Expand** — migration'lar additive/forward-only'dir (0001–0006 additive). `MIGRATION_DATABASE_URL`
   (flowpilot_migrator) ile: `python -m alembic -c apps/backend/alembic.ini upgrade head`.
3. **Deploy** — yeni application (API + worker) sürümünü yayına al.
4. **Verify** — health + smoke + `alembic current == head` (bkz. §6, §13).
5. **Contract** — MVP'de destructive/contract adımı YOK. Gelecekte eski kolon kaldırma **sonraki**
   release'e bırakılır; tek deploy'da destructive migration yapılmaz.

**Kurallar:** migration production'da uzun table lock yaratmaz; büyük index `CONCURRENTLY`
oluşturulur; web request içinde backfill YASAK; migration dosyaları silinip yeniden üretilmez;
downgrade runtime rollback aracı değildir (aşağıya bakın).

## 6. Health checks

| Endpoint | Anlam |
|---|---|
| `GET /health/live` | Process ayakta (liveness) — 200 `{"status":"ok"}` |
| `GET /health/ready` | Database'e gerçek `SELECT 1` (paylaşılan session factory) — hazırsa 200, değilse 503; hata detayı/DSN sızdırmaz |

Load balancer/orchestrator readiness'i trafik açmadan önce beklemeli. Worker'ın sağlığı
HTTP ile değil heartbeat healthcheck'i ile izlenir: bkz.
[worker-operations.md](worker-operations.md).

## 7. İlk tenant / bootstrap

- İlk kullanıcı Supabase üzerinden **signup + e-posta doğrulama** yapar.
- Giriş sonrası **onboarding** ile ilk organizasyonu oluşturur → kendisi aktif **owner** olur
  (tenant + owner membership aynı transaction'da).
- İlk approval akışından önce üç approval rolü (team_manager/finance/general_manager) aktif
  owner'a idempotent atanır (public endpoint değil).
- **Not:** rol yönetimi UI/API'si YOK; çok-kullanıcılı atama şu an kontrollü operasyon işidir
  (pilot readiness blocker'ı).

## 8. Supabase URL / redirect yapılandırma checklist'i

- Supabase projesinde **Site URL** = production web adresi.
- **Redirect allow-list**'e ekli: `<web-origin>/auth/callback` (staging + production ayrı ayrı).
- E-posta doğrulama şablonundaki bağlantı doğru ortama gider.
- JWT issuer/audience/algoritma backend `SUPABASE_JWT_*` ile uyumlu.
- Yalnız **publishable key** frontend'e; **service role key kullanılmaz**.

## 9. RLS ve database rol doğrulaması

- Uygulama YALNIZ `flowpilot_app` ile bağlanır; bu rol **NOSUPERUSER + NOBYPASSRLS**.
  Doğrula: `SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname='flowpilot_app';` → `(f, f)`.
- Her tenant tablosunda RLS **ENABLE + FORCE** ve tenant policy vardır; context yoksa **default deny**.
- `MIGRATION_DATABASE_URL` (migrator) runtime'da **kullanılmaz** — yalnız migration adımında.
- Cross-tenant IDOR: bir tenant'ın actor'ü başka tenant'ın kaynağını göremez/değiştiremez
  (staging checklist'te doğrulanır).

## 10. Logging ve secret-redaction

- Yapılandırılmış loglama (structlog). **Token/secret/parola/kişisel veri loglanmaz.**
- Audit log ≠ application log; audit **append-only** üründür (UPDATE/DELETE yok).
- Log toplayıcıya giden alanlarda redaction doğrulanır; access token/authorization header loga girmez.

## 11. Backup / restore yaklaşımı

- **Zamanlı tam yedek** + mümkünse PITR (WAL) — Render Managed PostgreSQL yedekleme özellikleriyle
  netleşir (ADR-010; kurulumda doğrulanır).
- Her deploy öncesi **anlık yedek**; restore prosedürü staging'de **test edilmiş** olmalı.
- Object storage (kullanılmaya başlandığında) ayrı yedek/lifecycle politikasına tabidir.
- Restore tatbikatı yapılmadan production'a geçilmez (pilot blocker'ı).

## 12. Rollback planı

- **Application rollback + forward fix** esastır. Migration **downgrade production rollback aracı
  DEĞİLDİR** (expand-only tasarım; downgrade veri kaybı riski taşır).
- Adımlar: (1) önceki application image/sürümüne dön; (2) şema additive olduğu için eski sürüm yeni
  şemayla uyumlu çalışır (expand→deploy sırası bunu garanti eder); (3) veri sorunu varsa **restore**
  (son doğrulanmış yedekten) owner onayıyla.
- Rollback tetikleyicileri: health/ready kalıcı fail · smoke test fail · beklenmeyen 5xx artışı ·
  cross-tenant/again auth anomalisi · migration verify uyuşmazlığı.

## 13. Post-deploy canlı acceptance checklist

Deploy sonrası [staging-acceptance-checklist.md](staging-acceptance-checklist.md) koşulur; özet:
- `/health/live` + `/health/ready` 200
- Login/signup/callback çalışıyor
- Organizasyon onboarding + aktif org context
- Talep oluşturma; eşik sınırları (9.999,99 / 10.000 / 50.000 / 50.000,01) doğru zincir
- Sequential approve + reject terminal
- Inbox isolation; timeline doğru
- Logout/login persistence
- Cross-tenant IDOR engelli; RLS context aktif
- `alembic current == head`; browser console temiz; backend 500 log taraması temiz; secret leak taraması temiz

## 14. Incident sırasında YAPILMAMASI gerekenler

- `docker system prune`, `docker volume prune`, volume silme, factory reset.
- Production'da ham SQL ile manuel veri düzeltme (versiyonlu, dry-run + audit'li admin repair command'ı olmadan).
- Migration downgrade ile "rollback".
- Audit kayıtlarını değiştirme/silme.
- Secret'ları log/rapor/çıktıya yazma.
- `git push --force` / paylaşılan history rewrite.
- Career Copilot altyapısına (container/volume/dosya) dokunma.
