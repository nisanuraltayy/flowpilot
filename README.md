# FlowPilot

**KOBİ'ler için çok kiracılı (multi-tenant) iş akışı, talep ve onay platformu.**

FlowPilot bir görev listesi uygulaması değildir. Değeri şudur: talepleri kurala göre yönlendirmek, onayları deterministik olarak yürütmek ve her kritik işlemi denetlenebilir kılmak. Dağınık e-posta, WhatsApp ve Excel üzerinden yürüyen satın alma, izin ve onay süreçlerinin yerini alır.

Bu repository **Career Copilot'tan tamamen bağımsızdır**.

---

## ⚠️ Mevcut geliştirme durumu

Şu ana kadar tamamlananlar:

| Aşama | Durum |
|---|---|
| Teknik PRD | ✅ Tamamlandı |
| Mimari kararlar (ADR-001…008) | ✅ Kabul edildi |
| Owner-approved MVP kapsamı | ✅ Tamamlandı |
| Backlog (16 epic, 48 story) | ✅ Tamamlandı |
| Environment preflight | ✅ Tamamlandı |
| Repository foundation bootstrap | ✅ Tamamlandı |
| Python fiziksel yerleşimi (ADR-009) | ✅ Tamamlandı |
| Backend scaffold + quality tooling | ✅ Tamamlandı |
| Local altyapı (PostgreSQL + MinIO) | ✅ Tamamlandı |
| Database foundation + organization creation core | ✅ Tamamlandı |
| Supabase Auth + `POST /v1/organizations` | ✅ Tamamlandı |
| Next.js web + Supabase login + organization onboarding | ✅ Tamamlandı |
| Canlı Supabase kabul testi (signup → doğrulama → login → onboarding) | ✅ Doğrulandı (2026-07-15) |
| Workflow runtime spike (ADR-004, 12/12 PASS) | ✅ Tamamlandı (2026-07-19) |
| Production Workflow Runtime Core (Epic E09) | ✅ Tamamlandı (2026-07-19) |
| **Purchase Request backend dikey dilimi (create → workflow → ilk onay task)** | ✅ **Tamamlandı (2026-07-19)** |
| Approval kararı + task inbox + audit timeline backend | ⏳ Sıradaki |

**İlk gerçek HTTP iş akışı çalışır durumdadır:**

```text
Bearer access token → Supabase JWT doğrulama (public JWKS, RS256/ES256)
  → internal FlowPilot user çözümleme/oluşturma (idempotent)
  → POST /v1/organizations → tenant + aktif owner membership (AYNI transaction)
  → HTTP 201
```

Bu akışı artık **Next.js web arayüzü** de sürer: kayıt ol → giriş yap → oturum
cookie'si → organizasyon adı → server action → Bearer token ile FastAPI →
`POST /v1/organizations` → başarı ekranı. Supabase yalnız kimlik doğrulaması
için kullanılır (service role key ve Supabase SDK'sı yok); browser'dan hiçbir
business tablosuna erişilmez — veri yalnız FastAPI üzerinden yönetilir.

> **FlowPilot MVP v0.1.0 — canlı uçtan uca kabul: ✅ PASS (2026-07-19, commit `c9043e8`).**
> Ayrıntı: [docs/releases/mvp-v0.1.0.md](docs/releases/mvp-v0.1.0.md). Gerçek cloud
> deployment YAPILMADI; hosting kararı LOCK-006 altında açık. Pilot öncesi işler:
> [docs/product/pilot-readiness.md](docs/product/pilot-readiness.md).

Tenant izolasyonu PostgreSQL RLS (ENABLE + FORCE) ile gerçek veritabanı
testlerinde kanıtlanmıştır. Alembic history: `0001`–`0006`. Roller:
`flowpilot_app`/`flowpilot_migrator` (ikisi de BYPASSRLS'siz).

Frontend, Purchase Request + kişisel onay kutusu + audit timeline akışını uçtan uca
sunar ([apps/web](apps/web/README.md)): giriş → aktif org çöz/seç → talep oluştur →
taleplerim → onay kutusu → onayla/reddet → durum + timeline. Aktif org, HttpOnly
cookie'de tutulur ama **authorization kaynağı değildir** (her istekte membership
yeniden doğrulanır).

Repository'de bulunmayanlar (kasıtlı): RBAC kataloğu, rol yönetimi UI/API, notification
delivery, `Dockerfile`, dark mode.

Backend domain kodu `identity`, `organization`, **`workflow_runtime` (Epic E09 —
production runtime core: definition versioning + immutable version, instance/task/event
lifecycle, transactional outbox + idempotent inbox, persisted timer, RLS, task assignee
pinning; `WorkflowRuntimePort` arkasında)**, **`purchase_request` (Create → workflow →
sıralı onay → timeline; `POST`/`GET`/liste/timeline endpoint'leri)**, **`approval` (role
assignment + atomik karar use-case + kişisel inbox; decision/inbox endpoint'leri)** ve
**`audit` (append-only writer + timeline read model)** modüllerindedir — migration `0006`.
Karar akışı runtime + PR status + ApprovalDecision + audit'i cross-module ATOMİK commit eder;
diğer 7 bounded context paketi boştur. Public runtime API'si yoktur. **Canlı Supabase kabul
testi 2026-07-15'te geçti:**
gerçek signup → e-posta doğrulama → login → ES256 token → `POST /v1/organizations`
→ 201; tenant + aktif owner membership aynı transaction'da oluştu. Ayrıntı:
[docs/open-questions.md](docs/open-questions.md) (OQ-009/OQ-010 — kapandı).

---

## Dokümanların okunma sırası

Bir çatışma olduğunda **üstteki kazanır**.

1. **[CLAUDE.md](CLAUDE.md)** — günlük geliştirme talimatı, aktif kararlar, karar kilitleri, yasaklar
2. **[AGENTS.md](AGENTS.md)** — AI coding agent çalışma sözleşmesi (bağlayıcı)
3. **[docs/product/mvp-scope-v0.1.md](docs/product/mvp-scope-v0.1.md)** — **owner-approved teslim kapsamı** (PRD'nin geniş MVP tanımının üzerinde önceliklidir)
4. **[docs/adr/](docs/adr/README.md)** — kabul edilmiş mimari kararlar
5. **[docs/architecture/domain-boundaries.md](docs/architecture/domain-boundaries.md)** — modül sahipliği, invariant'lar, state machine'ler
6. **[docs/architecture/dependency-rules.md](docs/architecture/dependency-rules.md)** — bağımlılık kuralları ve CI fitness function'ları
7. **[docs/backlog/](docs/backlog/epics.yaml)** — epic ve story'ler
8. **[docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md](docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md)** — araştırma, ürün vizyonu ve normatif mühendislik sözleşmesi
9. **[.claude/rules/](.claude/rules/architecture.md)** — mimari, güvenlik, test, veritabanı ve git kuralları

PRD **değiştirilmez**. Teslim kapsamı için `mvp-scope-v0.1.md`, mühendislik kuralları için PRD §32–§48 geçerlidir.

---

## Kabul edilmiş teknoloji kararları

| Karar | Seçim | ADR |
|---|---|---|
| Backend | Python + FastAPI + Pydantic + SQLAlchemy + Alembic | [ADR-001](docs/adr/ADR-001-backend-stack.md) |
| Frontend | Next.js + TypeScript | [ADR-002](docs/adr/ADR-002-frontend-stack.md) |
| Mimari | Modüler monolit + ayrı worker process'leri | [ADR-003](docs/adr/ADR-003-modular-monolith.md) |
| Workflow runtime | `WorkflowRuntimePort` arkasında custom PostgreSQL-backed runtime — **spike 12/12 geçti (2026-07-19), ADR-004 Accepted, LOCK-003 kapandı**. Production (E09) henüz yazılmadı. Camunda 8 elendi; Temporal yedek | [ADR-004](docs/adr/ADR-004-workflow-runtime-spike.md) |
| Authentication | **Supabase Auth — yalnız kimlik doğrulama.** Organization, membership, RBAC, authorization ve tenant modeli FlowPilot'ın kendi PostgreSQL'inde | [ADR-005](docs/adr/ADR-005-authentication-boundary.md) |
| Tenant izolasyonu | Application scope **+** PostgreSQL Row Level Security (defense-in-depth) | [ADR-006](docs/adr/ADR-006-postgresql-tenant-isolation.md) |
| Asenkron işlem | Transactional outbox + PostgreSQL-backed polling worker (broker yok) | [ADR-007](docs/adr/ADR-007-transactional-outbox.md) |
| Repository | Monorepo | [ADR-008](docs/adr/ADR-008-monorepo.md) |
| Python yerleşimi | **Tek distribution** (`flowpilot-backend`), tek import kökü `flowpilot`, bounded context'ler `flowpilot.modules.*` | [ADR-009](docs/adr/ADR-009-python-physical-layout.md) |

**MVP workflow node seti (yalnız 6):** `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`.
Kapsam dışı: parallel/join, quorum, sub-workflow, webhook, script, AI, DMN, görsel canvas.

**İlk dikey dilim:** Satın alma talebi — giriş → organizasyon/membership → talep → koşul → sıralı onay → state transition → bildirim → audit → timeline.

---

## Monorepo klasörleri

Fiziksel yerleşim kararı: [ADR-009](docs/adr/ADR-009-python-physical-layout.md) — **tek Python distribution**, tek import kökü (`flowpilot`).

```text
flowpilot/
├── apps/
│   ├── backend/                    # TEK Python distribution (flowpilot-backend)
│   │   ├── pyproject.toml          #   (henüz yok)
│   │   ├── alembic.ini             #   (henüz yok)
│   │   ├── migrations/             #   Alembic — TEK history
│   │   ├── src/flowpilot/          #   tek import kökü
│   │   │   ├── shared/             #     Money, TenantId, ClockPort, IdGeneratorPort
│   │   │   ├── observability/      #     log, metric, trace
│   │   │   ├── config/             #     env yükleme ve doğrulama
│   │   │   ├── modules/            #     13 bounded context — İŞ MANTIĞI BURADA
│   │   │   ├── api/                #     FastAPI composition root (iş mantığı YOK)
│   │   │   └── worker/             #     outbox/timer worker root (iş mantığı YOK)
│   │   └── tests/                  #   unit, integration, contract, security
│   └── web/                        # Next.js 16 web uygulaması (App Router, TS, Tailwind)
│       └── src/{app,components,features,lib}/
├── packages/
│   ├── contracts/                  # OpenAPI/AsyncAPI/JSON Schema + üretilen TS tipleri
│   └── ui/                         # Frontend design system
├── infra/containers/               # Dockerfile'lar, docker-compose (PostgreSQL + MinIO)
├── scripts/                        # Fitness check, contract lint, secret scan
├── tests/e2e/                      # Tarayıcı e2e (web + API birlikte)
├── docs/                           # PRD, ADR, mimari, kapsam, backlog
└── .claude/rules/                  # Agent için bağlayıcı kurallar
```

| Klasör | Sorumluluk |
|---|---|
| `apps/backend/src/flowpilot/modules/` | 13 bounded context. Her modül kendi tablolarına sahiptir; başka modülün tablosuna **yazamaz**. |
| `apps/backend/src/flowpilot/{api,worker}/` | İki composition root, **tek distribution**. İş mantığı içermezler; adapter wiring burada yapılır. |
| `apps/web/` | Next.js. Backend modüllerini import etmez; yalnız `packages/contracts` üzerinden konuşur. |
| `packages/` | Dil-nötr sözleşmeler (`contracts`) ve frontend design system (`ui`). |
| `infra/containers/` | Docker container tanımları. Migration'lar **`apps/backend/migrations/`** altındadır. |
| `scripts/` | Fitness check, contract lint, secret scan gibi doğrulama script'leri. |
| `tests/e2e/` | Web + API'yi birlikte süren tarayıcı testleri. Python testleri `apps/backend/tests/`'tedir. |
| `docs/` | Tek gerçek kaynak. Kod ile birlikte güncellenir. |

Her klasörün kendi `README.md`'si o klasörün **bağımlılık sınırını** açıklar. Bu sınırlar CI'da otomatik doğrulanacaktır ([dependency-rules.md](docs/architecture/dependency-rules.md), FF-01…FF-16).

---

## Import ve bağımlılık kuralları

```text
presentation ──┐
               ├──► application ──► domain   (domain hiçbir şeye bağımlı değil)
infrastructure ┘        │
                        └──► ports ◄── infrastructure IMPLEMENTE eder
```

```python
# ✅ composition root → application sınırı
from flowpilot.modules.approval.application.commands import DecideApprovalStep

# ❌ domain'de framework / ORM / provider SDK
from sqlalchemy import Column        # YASAK
from fastapi import Depends          # YASAK

# ❌ başka bir context'in domain veya infrastructure katmanı
from flowpilot.modules.approval.infrastructure.models import ApprovalStepRow   # YASAK
```

1. **Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK.**
2. Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır.
5. **Adapter wiring yalnız composition root'ta** yapılır.
6. **`PYTHONPATH` hack'i kullanılmaz** — editable install.
7. **Aynı bounded context için ikinci source of truth oluşturulmaz.**
8. Bounded context klasör adları **snake_case**'dir (tireli ad Python import yolunda kullanılamaz).

---

## Kurulum (Windows PowerShell)

Backend scaffold çalışır durumdadır. Frontend henüz yok.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "apps/backend[dev]"
```

Kalite kapıları:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/backend/tests
.\.venv\Scripts\python.exe -m ruff check apps/backend/src apps/backend/tests scripts
.\.venv\Scripts\python.exe -m ruff format --check apps/backend/src apps/backend/tests scripts
.\.venv\Scripts\python.exe -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
.\.venv\Scripts\lint-imports.exe --config apps/backend/pyproject.toml
.\.venv\Scripts\python.exe scripts/check_import_boundaries.py apps/backend/src
.\.venv\Scripts\python.exe -m flowpilot.worker --check
```

Ayrıntı: [apps/backend/README.md](apps/backend/README.md). `.venv` Git'e **eklenmez**. `.env.example` gerçek secret **içermez**.

### Frontend (Next.js)

```powershell
cd apps/web
npm install
Copy-Item .env.local.example .env.local   # .env.local git-ignored; Supabase değerlerini girin
npm run dev            # http://localhost:3000
npm run lint; npm run typecheck; npm run test; npm run build
```

Ayrıntı ve mimari: [apps/web/README.md](apps/web/README.md). Frontend yalnız **publishable** Supabase key kullanır; service role key **yoktur**.

### Local altyapı (PostgreSQL + MinIO)

```powershell
Copy-Item .env.example .env    # .env içinde local parolaları girin (git-ignored)
docker compose --env-file .env -f infra/containers/compose.yaml up -d
```

PostgreSQL `localhost:5432`, MinIO API `localhost:9000`, MinIO Console `localhost:9001`. Uygulama henüz bunlara **bağlanmaz**; schema/tablo/migration/bucket **yoktur**. Ayrıntı ve tüm komutlar: [infra/containers/README.md](infra/containers/README.md).

---

## Lisans

Özel (private). Tüm hakları saklıdır.
