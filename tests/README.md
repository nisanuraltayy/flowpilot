# tests/ — Uygulama Sınırını Aşan E2E Testleri

Repo kökündeki bu dizin **yalnızca web + API'yi birlikte** süren uçtan uca testleri barındırır.

| Dizin | Kapsam |
|---|---|
| [e2e/](e2e/README.md) | Tarayıcı akışı: Next.js UI → FastAPI → PostgreSQL → worker |

## Python testleri burada DEĞİL

Backend'in unit, integration, contract ve security testleri **`apps/backend/tests/`** altındadır ([ADR-009](../docs/adr/ADR-009-python-physical-layout.md)):

| Test türü | Yer |
|---|---|
| Unit | `apps/backend/tests/unit/` |
| Integration (PostgreSQL, RLS, outbox) | `apps/backend/tests/integration/` |
| Contract (port fake ↔ gerçek adapter) | `apps/backend/tests/contract/` |
| **Security (cross-tenant, negatif authz)** | `apps/backend/tests/security/` |

Gerekçe: tek pytest rootdir (`apps/backend`), tek `conftest.py` hiyerarşisi. İki rootdir, iki conftest karmaşası üretir.

## Bozulamaz kurallar

- **Failing test silinemez, `skip`/`xfail` ile geçilemez.**
- **Workflow runtime e2e testte tamamen mock'lanamaz** (PRD §39 anti-pattern'i). Kritik davranışı test etmeyen bir e2e testi, test değil dekordur.
- Testler birbirinden bağımsızdır; sıraya bağımlı test YASAK.

## Durum

Boş.
