# FlowPilot — Render Staging Planı (Frankfurt)

> Provider-specific staging planı. Hosting kararı: **Render (Frankfurt) + Supabase Auth
> (Frankfurt)** — [ADR-010](../adr/ADR-010-initial-hosting-and-data-region.md).
>
> ⚠️ **Gerçek deployment HENÜZ YAPILMADI.** Bu belge kurulum sırasını tarif eder; hiçbir
> Render kaynağı oluşturulmadı. `render.yaml` **bu aşamada yazılmaz** — önce gerçek Render
> kurulumunda servis **build/start komutları repository'den doğrulanır**, sonra (istenirse)
> IaC eklenir.
>
> 🔒 **Hiçbir gerçek secret, connection string veya ücret bilgisi bu belgeye yazılmaz** —
> yalnız değişken **adları** ve prosedür.

## 0. Ön koşul — private GitHub repository

Render, repository'ye bağlanarak build eder. Bu yüzden **önce private GitHub repository**
gerekir ([github-first-push-checklist.md](github-first-push-checklist.md)). CI'ın gerçek
runner'da yeşil olması, Render'a bağlanmadan önce beklenir.

## 1. Servisler (hepsi Region: **Frankfurt**)

| # | Render kaynağı | FlowPilot bileşeni | Not |
|---|---|---|---|
| 1 | **Managed PostgreSQL** | Uygulama veritabanı | İlk kaynak; **internal/private** bağlantı URL'i kullanılır |
| 2 | **Web Service** | FastAPI backend (`api`) | `flowpilot_app` (NOBYPASSRLS) rolüyle DB'ye bağlanır |
| 3 | **Background Worker** | Outbox/timer worker | `python -m flowpilot.worker --run` (always-on) |
| 4 | **Web Service** | Next.js frontend (`web`) | Backend'e **server-side** çağrı yapar |
| — | Supabase Auth | Kimlik doğrulama (Frankfurt) | Yeni kaynak değil; mevcut proje |

## 2. Build / start komutları — **repository'den doğrula**

Aşağıdaki komutlar repo'daki manifest'lerle **birebir doğrulanmalıdır** (uydurma yok):

- **Backend (api):** editable/standart install → `pip install -e "apps/backend"`;
  start → `uvicorn flowpilot.api.main:app --host 0.0.0.0 --port <RENDER_PORT>`.
  (Uygulama adı: [`apps/backend/README.md`](../../apps/backend/README.md) §Entrypoint'ler.)
- **Worker:** aynı install; start → `python -m flowpilot.worker --run`
  (`--check` yalnız doğrulama; `--run` sürekli dispatch).
- **Frontend (web):** `npm ci` (apps/web) → build `npm run build` → start `npm run start`.
  Node 20 (bkz. CI `frontend` job).

> Render'ın root/monorepo ayarı: her servis için **root directory** (ör. `apps/backend`,
> `apps/web`) ve build/start komutları Render panelinden ayarlanır. Bu değerler gerçek
> kurulumda panelde girilir; buraya secret yazılmaz.

## 3. Environment variable isimleri (yalnız ADLAR)

> Değerler Render'ın kendi env/secret yönetiminde tutulur; repository'ye yazılmaz.
> Tam açıklamalar: [deployment-runbook.md](deployment-runbook.md) §3.

**Backend (api) + worker:**
`APP_ENVIRONMENT` (=`staging`) · `DATABASE_URL` (internal/private, `flowpilot_app`) ·
`MIGRATION_DATABASE_URL` (yalnız migration adımı, `flowpilot_migrator`) · `SUPABASE_URL` ·
`SUPABASE_JWT_AUDIENCE` · `SUPABASE_JWT_ALLOWED_ALGORITHMS`.

**Frontend (web):**
`NEXT_PUBLIC_SUPABASE_URL` · `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` ·
`FLOWPILOT_API_BASE_URL` (server-only; backend web service'in **internal** URL'i) ·
`NEXT_PUBLIC_APP_URL` (web'in public URL'i).

**YASAK:** `SUPABASE_SERVICE_ROLE_KEY` / JWT secret hiçbir serviste kullanılmaz.

## 4. Internal / private DB URL

- Backend + worker, PostgreSQL'e Render'ın **internal** bağlantı adresiyle bağlanır (public
  internet'e açık external URL değil).
- DB rolü uygulamada **`flowpilot_app`** (NOSUPERUSER, NOBYPASSRLS). `flowpilot_migrator`
  yalnız migration adımında.
- Roller Render Managed PostgreSQL'de manuel/provisyon adımıyla oluşturulur
  (`scripts/provision_local_database.py` yalnız local/CI içindir; production role provisioning
  denetlenen ayrı bir süreçtir — ADR-006).

## 5. Alembic pre-deploy migration adımı

- Deploy sırasında **uygulama başlamadan önce** migration uygulanır:
  `python -m alembic -c apps/backend/alembic.ini upgrade head` (`MIGRATION_DATABASE_URL` ile).
- Expand-only; deploy öncesi **DB backup** (bkz. runbook §5, §11).
- Doğrulama: `alembic current == head (0006)`.

## 6. Health checks

- Backend health check path'i: **`/health/ready`** (readiness). Liveness: `/health/live`.
- Render, servis "healthy" olana dek trafiği açmamalı.

## 7. Supabase staging redirect URL checklist

- Supabase **Site URL** = web servisinin public URL'i (staging).
- **Redirect allow-list**'e: `<web-public-url>/auth/callback` (staging).
- E-posta doğrulama bağlantısı staging'e gider.
- JWT issuer/audience/algoritma backend `SUPABASE_JWT_*` ile uyumlu.
- Yalnız **publishable key** frontend'e.

## 8. Service-to-service URL

- Frontend → Backend çağrıları **server-side**'dır; `FLOWPILOT_API_BASE_URL` backend'in
  **internal** Render URL'ine ayarlanır (public üzerinden gereksiz tur atılmaz).
- Backend → PostgreSQL: internal DB URL.

## 9. Staging acceptance sırası

1. PostgreSQL kaynağı + roller hazır.
2. Migration `upgrade head` + `alembic current == 0006`.
3. Backend + worker deploy; `/health/ready` 200.
4. Frontend deploy; ana route yanıt veriyor.
5. Supabase redirect URL'leri ayarlı.
6. [staging-acceptance-checklist.md](staging-acceptance-checklist.md) baştan sona koşulur.

## 10. Rollback

- Render'da önceki başarılı deploy'a **rollback** (application rollback esas).
- Şema expand-only olduğundan eski sürüm yeni şemayla uyumludur.
- Veri sorunu → son doğrulanmış **backup**'tan restore (owner onayı).
- Migration **downgrade** rollback aracı DEĞİLDİR (runbook §12).

## 11. Ücretsiz kademe uyarısı

- Render ücretsiz servisleri **cold-start/uyku** davranışı taşır → yalnız **demo** için değerlendirilir.
- **Pilot öncesi always-on** servisler gerekir (özellikle **worker** ve **PostgreSQL**; uyuyan
  worker outbox dispatch'i geciktirir). Bu bir ücret/plan kararıdır (owner).

## 12. Bu planın YAPMADIKLARI

- `render.yaml` / IaC **oluşturmaz** (önce komutlar gerçek kurulumda doğrulanır).
- Gerçek Render kaynağı **oluşturmaz**, deploy **etmez**.
- Secret/connection string/ücret bilgisi **yazmaz**.
