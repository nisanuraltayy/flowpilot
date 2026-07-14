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

### Local altyapı

Integration testleri (henüz yok) gerçek PostgreSQL ve MinIO gerektirecek. Local servisler ayrı bir Compose projesiyle çalışır — uygulama **henüz bağlanmaz**:

```powershell
docker compose --env-file .env -f infra/containers/compose.yaml up -d
```

PostgreSQL `localhost:5432`, MinIO `localhost:9000` (API) / `localhost:9001` (console). Ayrıntı: [infra/containers/README.md](../../infra/containers/README.md).

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

## Bu scaffold'da BULUNMAYANLAR

Bilinçli olarak yok:

- Database bağlantısı, SQLAlchemy modeli, tablo — **yok**
- `alembic.ini`, `migrations/` — **yok**
- Tenant context, RLS, authorization — **yok**
- Supabase entegrasyonu, authentication kodu — **yok**
- Workflow runtime, purchase request, approval kodu — **yok**
- Outbox polling, gerçek worker loop, SIGTERM yönetimi — **yok**
- Dockerfile, docker-compose — **yok**
- Health dışında API endpoint'i — **yok**
- `integration/`, `contract/`, `security/` test klasörlerinde test — **yok** (sahte test eklenmedi)

**13 bounded context paketi boştur** (yalnız `__init__.py`). İçlerinde entity, model, repository, service, command, handler, SQLAlchemy tablosu veya iş kuralı **bulunmamaktadır**.
