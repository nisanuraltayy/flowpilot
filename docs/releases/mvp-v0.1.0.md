# FlowPilot MVP v0.1.0 — Release Kaydı

| Alan | Değer |
|---|---|
| **Release adı** | FlowPilot MVP v0.1.0 |
| **Release tarihi** | 2026-07-19 |
| **Kabul edilen temel commit** | `c9043e8` — feat: add purchase request and approval web experience |
| **Canlı acceptance sonucu** | ✅ **PASS** (owner onaylı, 2026-07-19) |
| **Migration seviyesi** | `0006` (head) |
| **Local tag** | `v0.1.0-mvp` (yalnız local; remote/push yapılmadı) |

> Bu kayıt bir **sürüm hazırlığı** belgesidir. Gerçek cloud deployment **YAPILMAMIŞTIR**.
> İlk hosting kararı verildi: **Render (Frankfurt)** (ADR-010; LOCK-006 kapandı) — kurulum/deploy
> henüz yapılmadı (bkz. §Bilinen riskler ve [pilot-readiness](../product/pilot-readiness.md)).

## Stack özeti

- **Backend:** Python 3.12/3.13 · FastAPI · Pydantic · SQLAlchemy 2.0 · Alembic (ADR-001).
  Modüler monolit (ADR-003), tek distribution `flowpilot` (ADR-009). API + worker aynı paketin
  iki composition root'u.
- **Frontend:** Next.js 16 (App Router) · React 19 · TypeScript (strict) · Tailwind CSS v4 (ADR-002).
- **Veri:** PostgreSQL (tek source of truth) · application-level tenant scope + **RLS ENABLE+FORCE**
  (ADR-006) · transactional outbox + idempotent inbox (ADR-007).
- **Auth:** Supabase Auth **yalnız authentication** (ADR-005); org/membership/RBAC/tenant
  FlowPilot'ın kendi PostgreSQL'inde. Domain Supabase SDK'sına bağımlı değil.
- **Workflow runtime:** custom PostgreSQL-backed runtime `WorkflowRuntimePort` arkasında (ADR-004).
- **Object storage:** S3-compatible port (local: MinIO) — MVP akışında kullanılmıyor, hazır.

## Teslim edilen özellikler

- Supabase login / signup (e-posta doğrulama akışı dâhil)
- Organizasyon onboarding ve **aktif organizasyon context'i** (cookie authz değil; her istekte
  membership yeniden doğrulanır)
- Multi-tenant izolasyon (application scope + PostgreSQL RLS)
- PostgreSQL workflow runtime (definition versioning + immutable version, instance/task/event
  lifecycle, persisted timer, outbox/inbox)
- Versioned purchase-approval workflow (Start / Form / Condition / Sequential Approval /
  Notification / End)
- Satın alma talebi oluşturma / liste / detay
- Tutar tabanlı sequential approval (10k / 50k eşik bantları, koşul definition'da)
- Kişisel görev inbox'ı (yalnız actor'a atanmış aktif görevler)
- Approve / reject kararları (atomik: runtime + PR status + ApprovalDecision + audit tek transaction)
- Idempotency (Idempotency-Key) ve concurrency koruması (unique + optimistic version CAS)
- Append-only audit timeline (deterministik sıra, tenant-scoped)
- Dashboard (sayımlar yalnız mevcut liste + inbox'tan türetilir; yeni analytics endpoint'i yok)
- Logout / login sonrası context + talep kalıcılığı

## Teslim EDİLMEYEN özellikler (bilinçli, MVP dışı)

Kullanıcı daveti · rol yönetimi UI/API'si · separation-of-duties enforcement (self-approval MVP'de
SERBEST — ASM-0016) · team/department · workflow designer · dosya ekleri · e-posta notification ·
billing · AI özellikleri · **production deployment**.

## Test sonuçları (release doğrulaması)

| Süit | Sonuç |
|---|---|
| Backend pytest | ✅ 259 passed |
| Frontend vitest | ✅ 105 passed (coverage ≥ %80 eşiği) |
| Spike regression (workflow-runtime) | ✅ 72 passed |
| ruff check / format · mypy strict · AST boundaries · import-linter · worker `--check` | ✅ temiz |
| Alembic current | ✅ 0006 (head) |
| npm audit `--audit-level=high` | ✅ exit 0 (yalnız 2 *moderate* transitive) |

Canlı uçtan uca kabul (2026-07-19): Senaryo A (12.500 ₺ iki adımlı → Onaylandı), Senaryo B
(60.000 ₺ → Reddedildi, terminal), Senaryo C (logout/login persistence) — tümü **PASS**; backend'de
beklenmeyen 500 yok, frontend runtime/compile hatası yok, secret sızıntısı yok.

## Bilinen riskler

- **Gerçek deployment yapılmadı.** İlk hosting kararı verildi (ADR-010 — Render Frankfurt;
  LOCK-006 kapandı); Render kaynaklarının kurulması ve deploy henüz yapılmadı.
- **AI provider kararı ertelendi** (LOCK-007) — AI MVP dışı; production entegrasyonu pilot sonrasına
  açıkça ertelendi (sessiz kapanış değil).
- **Separation-of-duties yok:** self-approval MVP'de owner onaylı geçici karar (ASM-0016); pilot
  öncesi yeniden değerlendirilecek.
- **Rol yönetimi UI/API'si yok:** approval rolleri ilk akışta owner'a idempotent atanır; çok-kullanıcılı
  atama için kontrollü operasyon prosedürü gerekir.
- **npm:** 2 *moderate* transitive advisory (next → postcss); high/critical yok.
- **CI henüz gerçek GitHub runner'da doğrulanmadı** (bu repo'da remote/push yapılmadı).

## Pilot öncesi kalan işler

Ayrıntı: [docs/product/pilot-readiness.md](../product/pilot-readiness.md). Özet: hosting/veri bölgesi
kararı · production DB backup politikası · CI'ın gerçek runner'da geçmesi · staging deploy · Supabase
production redirect URL'leri · separation-of-duties kararı · logging/monitoring · security headers ·
rate limiting değerlendirmesi · KVKK veri envanteri · destek/incident iletişimi.

## Rollback ve veri koruma notları

- Migration'lar **expand-only / forward-only**; rollback = application rollback + forward fix
  (bkz. [deployment-runbook](../operations/deployment-runbook.md) §Rollback).
- Deploy öncesi **DB backup zorunlu**; destructive migration tek deploy'da yapılmaz.
- Audit tablosu append-only (grant + trigger); UPDATE/DELETE yolu yoktur.
- Bu release **tag'i local**'dir; kod ve migration dosyaları `c9043e8`'de dondurulmuştur — 0001–0006
  değişmez.
