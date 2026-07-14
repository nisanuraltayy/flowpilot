# apps/backend — FlowPilot Backend (tek Python distribution)

**Distribution:** `flowpilot-backend` · **Import kökü:** `flowpilot` · **Yerleşim kararı:** [ADR-009](../../docs/adr/ADR-009-python-physical-layout.md)

Stack: Python + FastAPI + Pydantic + SQLAlchemy + Alembic ([ADR-001](../../docs/adr/ADR-001-backend-stack.md)).

## Yapı

```text
apps/backend/
├── pyproject.toml            # TEK manifest (henüz yok)
├── alembic.ini               # (henüz yok)
├── migrations/               # Alembic — TEK history (henüz yok)
├── src/
│   └── flowpilot/            # tek import kökü
│       ├── shared/           # Money, TenantId, ClockPort, IdGeneratorPort, error base
│       ├── observability/    # structured log, metric, trace
│       ├── config/           # env yükleme ve doğrulama
│       ├── modules/          # 13 bounded context — iş mantığı BURADA
│       ├── api/              # FastAPI composition root  (İŞ MANTIĞI YOK)
│       └── worker/           # outbox/timer worker root  (İŞ MANTIĞI YOK)
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    └── security/
```

## Neden tek distribution

`api` ve `worker` **aynı domain kodunu** kullanır. Tek distribution, kod kopyalamayı **yapısal olarak imkânsız** kılar — "aynı bounded context için iki source of truth" yasağı disipline bırakılmaz.

`shared`, `observability`, `config` ve test altyapısı **ayrı distribution değildir**. Solo developer için 4+ `pyproject.toml` + editable install zinciri, hiçbir mimari fayda üretmeden günlük iş akışını yavaşlatır.

## İki composition root, tek paket

| | Entrypoint | Sorumluluk |
|---|---|---|
| `flowpilot.api` | `flowpilot.api.main:app` (uvicorn) | HTTP routing, token doğrulama, `TenantContext`, policy çağrısı |
| `flowpilot.worker` | `python -m flowpilot.worker` | Outbox dispatcher, timer worker, event consumer |

Aynı image, farklı `CMD` — ADR-003'ün "aynı kod tabanı, ayrı process" kararının karşılığı.

## Bağlayıcı import kuralları

1. **Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK.**
2. Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır.
5. **Adapter wiring yalnız composition root'ta** (`api/deps.py`, `worker/wiring.py`).
6. **`PYTHONPATH` hack'i kullanılmaz** — editable install (`pip install -e apps/backend`).
7. **Aynı bounded context için ikinci source of truth oluşturulmaz.**

Bu kurallar CI'da otomatik doğrulanır: [dependency-rules.md](../../docs/architecture/dependency-rules.md).

## Durum

**Boş.** `pyproject.toml`, `alembic.ini`, `migrations/`, `__init__.py` ve kaynak kodu **henüz oluşturulmadı** — backend scaffold owner onayı bekliyor.
