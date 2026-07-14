# Architecture Decision Records (ADR)

Bu dizin FlowPilot'ın mimari kararlarını tutar. ADR'ler **kaynak öncelik sırasında PRD'nin üzerindedir** (yalnız güvenlik/hukuki zorunluluklar ADR'nin üzerindedir — bkz. [CLAUDE.md](../../CLAUDE.md) §2).

## Süreç

1. Bir karar kilidi (LOCK) veya mimari çatallanma tespit edilir.
2. Seçenekler **aynı kriter setiyle** karşılaştırılır; gerekirse önce teknik spike yapılır.
3. ADR yazılır ve `Proposed` durumuna alınır.
4. Owner kararı sonrası `Accepted` olur; kilit kapanır.
5. Karar değişirse ADR **silinmez**. Yeni ADR yazılır; eskisi `Superseded by ADR-xxx` olarak işaretlenir.

## Durumlar

- `Proposed` — öneri hazır, owner kararı bekliyor. Üretim kodu bu karara dayandırılamaz.
- `Accepted` — bağlayıcı.
- `Accepted (conditional)` — bağlayıcı, ancak bir spike/exit criterion şartına bağlı.
- `Superseded` — yerini başka ADR aldı.
- `Rejected` — değerlendirildi, seçilmedi. Gerekçe korunur.

## Kayıt

| ADR | Başlık | Durum | Kapattığı kilit |
|---|---|---|---|
| [ADR-001](ADR-001-backend-stack.md) | Backend stack: Python + FastAPI + Pydantic + SQLAlchemy + Alembic | Accepted | LOCK-001 |
| [ADR-002](ADR-002-frontend-stack.md) | Frontend stack: Next.js + TypeScript | Accepted | LOCK-002 |
| [ADR-003](ADR-003-modular-monolith.md) | Modüler monolit + arka plan worker'ları | Accepted | — |
| [ADR-004](ADR-004-workflow-runtime-spike.md) | Workflow runtime: `WorkflowRuntimePort` arkasında custom PostgreSQL-backed runtime; önce spike | Accepted (conditional) | LOCK-003 (koşullu) |
| [ADR-005](ADR-005-authentication-boundary.md) | Authentication boundary: **Supabase Auth** + FlowPilot-owned authorization | **Accepted** | LOCK-004 |
| [ADR-006](ADR-006-postgresql-tenant-isolation.md) | Tenant izolasyonu: application scope + PostgreSQL RLS | Accepted | — |
| [ADR-007](ADR-007-transactional-outbox.md) | Transactional outbox + PostgreSQL-backed polling worker | Accepted | LOCK-005 |
| [ADR-008](ADR-008-monorepo.md) | Monorepo | Accepted | LOCK-008 |
| [ADR-009](ADR-009-python-physical-layout.md) | Python fiziksel yerleşimi: tek distribution (`flowpilot-backend`), tek import kökü `flowpilot`, bounded context'ler `flowpilot.modules.*` | Accepted | — (ADR-008'i tamamlar) |

## Hâlâ açık kilitler

- **LOCK-006** — Hosting ve veri bölgesi. Deployment provider-neutral kalır; ilk aday Render.
- **LOCK-007** — AI provider ve veri politikası. AI özellikleri gerçek MVP dışındadır.
- **LOCK-003** — Koşullu: workflow runtime spike'ın 12/12 exit criterion'u geçmesine bağlı.

Kapanan kilitler: LOCK-001 (ADR-001), LOCK-002 (ADR-002), **LOCK-004 (ADR-005 — Supabase Auth)**, LOCK-005 (ADR-007), LOCK-008 (ADR-008).

## Kapsam kaynağı

Teslim edilecek kapsam için bağlayıcı doküman: [docs/product/mvp-scope-v0.1.md](../product/mvp-scope-v0.1.md) (owner-approved; PRD §7.1/§24'ün üzerinde önceliklidir).

## Şablon

```markdown
# ADR-XXX — Başlık

- **Durum:** Proposed | Accepted | Accepted (conditional) | Superseded | Rejected
- **Tarih:** YYYY-MM-DD
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-XXX
- **İlgili PRD bölümleri:** §X

## Bağlam
## Değerlendirilen seçenekler
## Karar
## Gerekçe
## Sonuçlar (pozitif / negatif)
## Uyum kuralları (agent için bağlayıcı)
## Yeniden değerlendirme tetikleyicileri
```
