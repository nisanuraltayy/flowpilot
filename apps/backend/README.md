# apps/backend — FlowPilot Backend (tek Python distribution)

**Distribution:** `flowpilot-backend` · **Import kökü:** `flowpilot` · **Yerleşim kararı:** [ADR-009](../../docs/adr/ADR-009-python-physical-layout.md)

Stack: Python 3.12–3.13 + FastAPI + Pydantic + SQLAlchemy + Alembic ([ADR-001](../../docs/adr/ADR-001-backend-stack.md)).

> ⚠️ **Bu bir scaffold'dur.** Health endpoint'leri ve worker `--check` dışında hiçbir özellik yoktur. Domain modüllerinde **production business logic bulunmamaktadır**.

---

## Kurulum (Windows PowerShell)

`.venv` **repository kökünde** oluşturulur ve Git'e eklenmez.

```powershell
# repo kökünde
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "apps/backend[dev]"
```

Editable install (`-e`) sayesinde `flowpilot` paketi doğrudan `apps/backend/src`'ten çözülür. **`PYTHONPATH` hack'i kullanılmaz** (ADR-009).

### Local altyapı ve database foundation

```powershell
# 1) Servisleri başlat (PostgreSQL + MinIO)
docker compose --env-file .env -f infra/containers/compose.yaml up -d

# 2) Rolleri provision et (idempotent; LOCAL DEVELOPMENT aracı)
.\.venv\Scripts\python.exe scripts/provision_local_database.py

# 3) Migration'ları uygula
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head

# Durum / geri alma
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini downgrade -1
```

PostgreSQL `localhost:5432`, MinIO `localhost:9000` (API) / `localhost:9001` (console). Ayrıntı: [infra/containers/README.md](../../infra/containers/README.md).

### Database rol ayrımı (ADR-006)

| Rol | Amaç | Yetkiler |
|---|---|---|
| `flowpilot_admin` | Bootstrap superuser — **yalnız provisioning** | superuser (container zorunluluğu) |
| `flowpilot_migrator` | Alembic DDL (`MIGRATION_DATABASE_URL`) | NOSUPERUSER, **NOBYPASSRLS**, NOCREATEDB, NOCREATEROLE + şemada CREATE |
| `flowpilot_app` | Uygulama DML (`DATABASE_URL`) | NOSUPERUSER, **NOBYPASSRLS**, NOCREATEDB, NOCREATEROLE + yalnız DML grant'ları |

**Uygulama `flowpilot_admin` ile ASLA bağlanmaz.** Tenant tablolarında RLS `ENABLE` **+ `FORCE`**'tur — FORCE, tablo sahibinin (migrator) bile RLS'i bypass edememesini sağlar (testle kanıtlı).

### RLS transaction context'i

Tenant scope, PostgreSQL **transaction-local** ayarlarla taşınır ve transaction bitince otomatik sıfırlanır (bağlantı havuzuna sızmaz):

```sql
SELECT set_config('app.current_actor_id',  '<user-uuid>',   true);
SELECT set_config('app.current_tenant_id', '<tenant-uuid>', true);
```

- Context YOKSA erişim **varsayılan olarak reddedilir** (0 satır).
- Policy karşılaştırmaları **metin** üzerinden yapılır (`id::text = current_setting(...)`) — boş/NULL context hata değil, güvenli red üretir.
- `UnitOfWork.set_actor_context / set_tenant_context` bu ayarları yönetir.

### İlk business use-case: CreateOrganization

`flowpilot.modules.organization.application.handler.CreateOrganizationHandler`:
tenant + aktif owner membership **aynı transaction'da** oluşur; herhangi bir adım
başarısızsa ikisi de rollback edilir. Duplicate membership DB unique constraint'i
ile engellenir. **Henüz HTTP endpoint'i ve Supabase auth YOKTUR** — use-case yalnız
application katmanındadır; `POST /v1/organizations` bir sonraki aşamada bağlanacaktır.

### Integration testleri (Testcontainers)

`apps/backend/tests/integration/` gerçek PostgreSQL'i **Testcontainers** ile ayağa
kaldırır — local development veritabanına **dokunmaz**. Docker yoksa testler
HATA verir, sessizce geçmez. Kapsam: migration upgrade/downgrade, rol güvenliği,
RLS (context'siz red, cross-tenant izolasyon, owner-bypass engeli), atomiklik,
rollback ve duplicate membership.

## Komutlar

```powershell
# Testler (coverage dahil)
.\.venv\Scripts\python.exe -m pytest apps/backend/tests

# Lint
.\.venv\Scripts\python.exe -m ruff check apps/backend/src apps/backend/tests scripts

# Format (kontrol / uygulama)
.\.venv\Scripts\python.exe -m ruff format --check apps/backend/src apps/backend/tests scripts
.\.venv\Scripts\python.exe -m ruff format apps/backend/src apps/backend/tests scripts

# Type check (strict) — config apps/backend'de olduğu için --config-file zorunlu
.\.venv\Scripts\python.exe -m mypy --config-file apps/backend/pyproject.toml apps/backend/src

# Import boundary (import-linter contract'ları)
.\.venv\Scripts\lint-imports.exe --config apps/backend/pyproject.toml

# Import boundary (AST — katman kuralları; bkz. aşağıda)
.\.venv\Scripts\python.exe scripts/check_import_boundaries.py apps/backend/src

# Worker doğrulaması (worker loop BAŞLATMAZ)
.\.venv\Scripts\python.exe -m flowpilot.worker --check
```

## Entrypoint'ler

| | Entrypoint |
|---|---|
| API | `flowpilot.api.main:app` (uvicorn ile çalıştırılır; scaffold aşamasında server başlatılmaz) |
| Worker | `python -m flowpilot.worker --check` |

## Health endpoint'leri

Authentication ve tenant context **gerektirmezler**; iş mantığı **içermezler**.

| Endpoint | Yanıt |
|---|---|
| `GET /health/live` | `{"status": "ok"}` |
| `GET /health/ready` | `{"status": "ready", "checks": {}}` |

**Readiness şu an statiktir.** PostgreSQL, Supabase veya object storage **kontrol edilmez** — bu bağımlılıklar henüz yok. Kontroller eklendikçe `checks` doldurulacaktır.

Uygulama **import edilirken hiçbir database/provider bağlantısı kurulmaz** (testle doğrulanır).

## Src-layout

```text
apps/backend/
├── pyproject.toml            # tek manifest: deps + ruff + mypy + pytest + import-linter
├── src/flowpilot/            # ← import kökü (paket burada, repo kökünde değil)
│   ├── shared/               # (boş) Money, TenantId, ClockPort, IdGeneratorPort gelecek
│   ├── observability/        # (boş) structlog tabanlı log/metric/trace gelecek
│   ├── config/settings.py    # Pydantic Settings — frozen, mutable global YOK
│   ├── modules/              # 13 bounded context — HEPSİ BOŞ (yalnız __init__.py)
│   ├── api/                  # FastAPI composition root — iş mantığı YOK
│   └── worker/               # worker composition root — iş mantığı YOK
└── tests/{unit,integration,contract,security}/
```

**Neden src-layout:** testler *kurulmuş* paketi import eder, çalışma dizinindeki klasörü değil. Bu, "yerelde çalışıyor ama Docker'da import hatası" sınıfı hataları yerelde yakalatır.

## Dependency grupları ve gerekçeleri

### Runtime

| Paket | Neden |
|---|---|
| `fastapi` | HTTP API (ADR-001). Yalnız presentation katmanında. |
| `uvicorn[standard]` | ASGI server. |
| `pydantic` | Request/response DTO, form schema ve workflow definition JSON doğrulaması — ADR-001'in ana gerekçesi. |
| `pydantic-settings` | Environment'tan tip güvenli, doğrulanmış ayar yükleme. |
| `sqlalchemy` | Persistence — **yalnız** infrastructure katmanında (ADR-001). |
| `alembic` | Versiyonlu migration. **Bu aşamada yalnız dependency olarak var**; `alembic.ini` ve `migrations/` henüz oluşturulmadı. |
| `psycopg[binary]` | PostgreSQL sürücüsü. RLS ve `FOR UPDATE SKIP LOCKED` (ADR-006, ADR-007) için PostgreSQL'e özgü davranış gerekir. |
| `structlog` | Structured logging abstraction'ı. **Henüz wiring yok** — `flowpilot.observability` story'sinde bağlanacak. |

### Development

| Paket | Neden |
|---|---|
| `pytest`, `pytest-asyncio`, `pytest-cov` | Test çalıştırma, async test desteği, coverage. |
| `httpx2` | Starlette 1.3+ `TestClient` **`httpx2` ister**; `httpx` ile kullanım DeprecationWarning üretir ve uyarılar hataya çevrilir. |
| `ruff` | Lint + formatter (tek araç). |
| `mypy` | Strict type check. |
| `import-linter` | Mimari import contract'ları. |
| `testcontainers[postgres]` | Gerçek PostgreSQL'e karşı integration testleri. **Henüz kullanılmıyor** — local altyapı aşamasında devreye girecek. |

Gereksiz dependency eklenmemiştir. `structlog`, `alembic` ve `testcontainers` şu an *kullanılmıyor* ancak bilinçli olarak **şimdi seçilmiştir**: sonraki story'lerde stack kararı yeniden tartışılmasın diye.

## Import kuralları (bağlayıcı)

1. **Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK.**
2. Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır.
5. **Adapter wiring yalnız composition root'ta** (`api/deps.py`, `worker/wiring.py`).
6. **`PYTHONPATH` hack'i YASAK** — editable install.
7. **Aynı bounded context için ikinci source of truth YASAK.**

### Bu kurallar nasıl zorlanıyor

| Araç | Zorladığı |
|---|---|
| **import-linter** (4 contract) | Katman sırası (`api`/`worker` → `modules` → `config`/`observability` → `shared`), `api` ↔ `worker` bağımsızlığı, `flowpilot.shared`'ın saflığı, `flowpilot.modules`'ün web framework'e bağımlı olamaması |
| **`scripts/check_import_boundaries.py`** (AST) | Yukarıdaki 1–3 numaralı **katman** kuralları |

**Neden iki araç:** bounded context'ler şu an boş paketlerdir; `domain`/`application`/`infrastructure` alt paketleri henüz yok. import-linter var olmayan modülü çözemediği için katman bazlı contract'ları **henüz ifade edemez**. Kontrolü sessizce kaldırmak yerine, aynı kuralları boş pakette de çalışan salt-okunur bir AST kontrolüyle zorluyoruz. Layer paketleri oluştuğunda kuralların import-linter'a taşınması değerlendirilecektir — bkz. [ASM-0011](../../docs/assumptions.md).

## Bu aşamada BULUNMAYANLAR

Bilinçli olarak yok:

- **HTTP organization endpoint'i** (`POST /v1/organizations`) — sonraki aşama
- **Supabase entegrasyonu, authentication, token doğrulama** — sonraki aşama
- Login/register/password/session/e-posta doğrulama kodu
- Team/department, permission/RBAC kataloğu
- Workflow runtime, purchase request, approval, task kodu
- Outbox polling, gerçek worker loop, SIGTERM yönetimi
- Audit, notification, MinIO bucket / object storage SDK kodu
- Dockerfile, backend container image
- Health dışında API endpoint'i

**Var olan domain kodu:** yalnız `identity` (minimal User) ve `organization`
(Organization/Membership + CreateOrganization use-case'i). Diğer 11 bounded
context paketi hâlâ boştur.
