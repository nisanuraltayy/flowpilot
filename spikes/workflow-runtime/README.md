# ⚠️ SPIKE — Workflow Runtime (GEÇİCİ, PRODUCTION DEĞİL)

**Bu dizin bir teknik spike'tır (ADR-004, Epic E08, LOCK-003).**

- **Production kodu DEĞİLDİR.** `flowpilot` paketinden import edilmez, `flowpilot.api`
  veya `flowpilot.worker`'a wiring yapılmaz, production Alembic history'sine
  (0001/0002) hiçbir tablo eklemez.
- Amaç: custom PostgreSQL-backed workflow runtime yaklaşımının
  [spike planındaki](../../docs/architecture/workflow-runtime-spike-plan.md)
  **12 exit criterion'u** (SPK-01…SPK-12) karşılayıp karşılamadığını **kanıtlamak**.
- Çıktı **karar ve kanıttır**, ürün değildir:
  [workflow-runtime-spike-results.md](../../docs/architecture/workflow-runtime-spike-results.md).
- Spike başarılı olsa bile buradaki kod production'a **kopyalanmaz**; production
  implementasyonu (E09) `WorkflowRuntimePort` arkasında sıfırdan, üretim kalitesiyle
  yazılır. Bu dizin, karar verildikten sonra silinmeye adaydır.

## Yapı

```text
spikes/workflow-runtime/
├── pyproject.toml            # ayrı mini distribution: flowpilot-spike-workflow-runtime
├── src/spike_runtime/        # import kökü: spike_runtime (flowpilot'tan tamamen ayrı)
│   ├── definition.py         #   workflow definition yükleme + hash + node whitelist
│   ├── conditions.py         #   güvenli, deterministik condition evaluator (eval YOK)
│   ├── schema.py             #   spike'a özel DDL + roller + RLS (production migration DEĞİL)
│   ├── engine.py             #   instance lifecycle, sequential approval, terminal guard
│   ├── dispatcher.py         #   outbox claim (FOR UPDATE SKIP LOCKED), idempotent inbox, timer
│   ├── worker_main.py        #   crash-recovery testleri için gerçek subprocess entrypoint
│   └── fixtures/             #   satın alma workflow definition fixture'ları (eşikler BURADA)
└── tests/
    ├── unit/                 #   evaluator + definition + statik güvenlik kontrolleri
    └── integration/          #   Testcontainers PostgreSQL — SPK-01..12 + benchmark
```

## Kurulum ve çalıştırma (repo kökünden, mevcut `.venv` ile)

Yeni runtime dependency **yoktur** — SQLAlchemy/psycopg/pytest/testcontainers zaten
backend dev ortamında kuruludur. Spike yalnız kendi paketini editable kurar:

```powershell
.\.venv\Scripts\python.exe -m pip install -e spikes/workflow-runtime
.\.venv\Scripts\python.exe -m pytest spikes/workflow-runtime/tests
.\.venv\Scripts\python.exe -m ruff check spikes/workflow-runtime/src spikes/workflow-runtime/tests
.\.venv\Scripts\python.exe -m ruff format --check spikes/workflow-runtime/src spikes/workflow-runtime/tests
.\.venv\Scripts\python.exe -m mypy --config-file spikes/workflow-runtime/pyproject.toml spikes/workflow-runtime/src
```

Integration testleri **gerçek PostgreSQL** ister (Testcontainers). Docker yoksa testler
HATA verir — sessizce geçmez (bilinçli). Local development veritabanına dokunulmaz.

## Sınırlar

- Onay eşikleri (10.000 / 50.000 TL) Python koduna **hard-code edilmemiştir**;
  `src/spike_runtime/fixtures/purchase_request_v1.json` workflow definition'ından okunur.
- Para **minor unit (kuruş) + ISO-4217 currency** olarak taşınır; float YOK.
- Tüm timestamp'ler UTC (`timestamptz`); naive datetime YOK.
- `eval`/`exec` YOK (testte statik olarak da doğrulanır).
- Spike rollerinde `BYPASSRLS` YOK; tenant tablolarında RLS **ENABLE + FORCE**.
