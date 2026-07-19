# scripts/ — Geliştirme ve Doğrulama Script'leri

Kalite kapılarını **çalıştırılabilir** hâle getiren script'ler. CI ve local'de **aynı** script'ler çalışır — "bende çalışıyordu" durumunu engellemek için.

## Mevcut script'ler

| Script | Rol |
|---|---|
| **`check_import_boundaries.py`** | **Çalışıyor.** Salt-okunur AST analizi ile katman import kurallarını zorlar: (1) domain'de FastAPI/SQLAlchemy/Supabase importu yasak, (2) cross-context `domain`/`infrastructure` importu yasak, (3) composition root domain/infrastructure'a erişemez (wiring hariç). import-linter bu kuralları boş paketlerde ifade edemediği için vardır — bkz. [ASM-0011](../docs/assumptions.md). Production logic içermez. |
| **`provision_local_database.py`** | **Çalışıyor.** LOCAL development + CI için `flowpilot_migrator` ve `flowpilot_app` rollerini idempotent provision eder (NOSUPERUSER, NOBYPASSRLS). Parola değerleri env'den alınır, terminale yazılmaz. |
| **`release_verify.ps1`** | **Çalışıyor.** Release doğrulaması: tüm backend + frontend kalite kapılarını fail-fast çalıştırır (aşağıya bakın). |

```powershell
.\.venv\Scripts\python.exe scripts/check_import_boundaries.py apps/backend/src
```

### `release_verify.ps1` — release doğrulaması

Backend (ruff/format/mypy/AST-boundaries/import-linter/worker `--check`/pytest) + alembic
current (yalnız okuma, `0006` beklenir) + frontend (lint/typecheck/test/coverage/build/audit
high) + git özetini **fail-fast** çalıştırır. Docker Desktop çalışıyor olmalı (integration
testleri Testcontainers kullanır).

```powershell
# repo kökünden
powershell -ExecutionPolicy Bypass -File scripts\release_verify.ps1
```

**Güvenli davranış:** secret/env DEĞERLERİ yazdırılmaz; Docker volume silmez, prune yapmaz;
migration **downgrade** yapmaz (yalnız `alembic current` okur); remote/push yapmaz.
CI eşdeğeri: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Üretilecek script'ler

| Script | Rol |
|---|---|
| `check-architecture.*` | Kalan mimari fitness function'ları: FF-03…FF-16 ([dependency-rules.md](../docs/architecture/dependency-rules.md)) |
| `check-contracts.*` | OpenAPI lint + breaking-change diff + AsyncAPI validation |
| `check-secrets.*` | Secret tarama (her commit'te) |
| `verify-migrations.*` | Boş DB ve önceki release şeması üzerinde migration testi |
| `check-tenant-tables.*` | Her tenant tablosunda `tenant_id` + RLS politikası var mı (FF-03, FF-04) |

## Kritik fitness function'lar (hatırlatma)

- **FF-01** Domain katmanında `sqlalchemy` / `fastapi` / Supabase SDK importu **yok**
- **FF-08** Kod tabanında `eval(` / `exec(` **yok**
- **FF-09** Para alanlarında `float` **yok**
- **FF-11** Published workflow tablolarına `UPDATE` çalıştıran kod **yok**

## Kural

**Bu script'ler kapatılamaz, atlanamaz veya "geçici olarak" devre dışı bırakılamaz.** Kırmızıysa merge yok.

Windows script'leri `.ps1` uzantılıdır ve `.gitattributes` gereği **CRLF** ile saklanır.

## Durum

Boş.
