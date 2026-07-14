# FlowPilot

**KOBİ'ler için çok kiracılı (multi-tenant) iş akışı, talep ve onay platformu.**

FlowPilot bir görev listesi uygulaması değildir. Değeri şudur: talepleri kurala göre yönlendirmek, onayları deterministik olarak yürütmek ve her kritik işlemi denetlenebilir kılmak. Dağınık e-posta, WhatsApp ve Excel üzerinden yürüyen satın alma, izin ve onay süreçlerinin yerini alır.

Bu repository **Career Copilot'tan tamamen bağımsızdır**.

---

## ⚠️ Mevcut geliştirme durumu

> **Bu repository'de henüz production kodu YOKTUR.**

Şu ana kadar tamamlananlar:

| Aşama | Durum |
|---|---|
| Teknik PRD | ✅ Tamamlandı |
| Mimari kararlar (ADR-001…008) | ✅ Kabul edildi |
| Owner-approved MVP kapsamı | ✅ Tamamlandı |
| Backlog (16 epic, 48 story) | ✅ Tamamlandı |
| Environment preflight | ✅ Tamamlandı |
| **Repository foundation bootstrap** | ✅ **Bu aşama** |
| Bootstrap doğrulaması | ⏳ Sıradaki |
| Backend / frontend scaffold | ⛔ Henüz başlamadı |

Repository'de bulunmayanlar (kasıtlı): kaynak kodu, `pyproject.toml`, `package.json`, `Dockerfile`, `docker-compose.yml`, migration, dependency.

**Sonraki aşama scaffold DEĞİLDİR.** Önce bu bootstrap'ın doğrulanması gerekir (klasör sınırları, satır sonları, secret taraması, ilk commit). Scaffold ayrıca onaylanacaktır.

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
| Workflow runtime | `WorkflowRuntimePort` arkasında custom PostgreSQL-backed runtime — **önce spike (12/12 exit criteria)**. Camunda 8 elendi; Temporal yedek | [ADR-004](docs/adr/ADR-004-workflow-runtime-spike.md) |
| Authentication | **Supabase Auth — yalnız kimlik doğrulama.** Organization, membership, RBAC, authorization ve tenant modeli FlowPilot'ın kendi PostgreSQL'inde | [ADR-005](docs/adr/ADR-005-authentication-boundary.md) |
| Tenant izolasyonu | Application scope **+** PostgreSQL Row Level Security (defense-in-depth) | [ADR-006](docs/adr/ADR-006-postgresql-tenant-isolation.md) |
| Asenkron işlem | Transactional outbox + PostgreSQL-backed polling worker (broker yok) | [ADR-007](docs/adr/ADR-007-transactional-outbox.md) |
| Repository | Monorepo | [ADR-008](docs/adr/ADR-008-monorepo.md) |

**MVP workflow node seti (yalnız 6):** `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`.
Kapsam dışı: parallel/join, quorum, sub-workflow, webhook, script, AI, DMN, görsel canvas.

**İlk dikey dilim:** Satın alma talebi — giriş → organizasyon/membership → talep → koşul → sıralı onay → state transition → bildirim → audit → timeline.

---

## Monorepo klasörleri

```text
flowpilot/
├── apps/          # Deployable birimler (composition root)
│   ├── api/       #   FastAPI — senkron HTTP API
│   ├── worker/    #   Outbox dispatcher, timer worker, event consumer
│   └── web/       #   Next.js kullanıcı uygulaması
├── modules/       # Bounded context'ler — iş mantığının yaşadığı yer
├── packages/      # Paylaşılan sözleşmeler ve altyapı paketleri
├── infra/         # Container tanımları ve migration'lar
├── scripts/       # Geliştirme ve doğrulama script'leri
├── tests/         # Uygulama sınırını aşan testler (e2e, güvenlik)
├── docs/          # PRD, ADR, mimari, kapsam, backlog
└── .claude/rules/ # Agent için bağlayıcı kurallar
```

| Klasör | Sorumluluk |
|---|---|
| `apps/` | Yalnız **composition root**. İş mantığı içermez; modülleri birbirine bağlar ve dış dünyaya açar. |
| `modules/` | 13 bounded context. Her modül kendi tablolarına sahiptir; başka modülün tablosuna **yazamaz**. |
| `packages/` | Sözleşmeler (OpenAPI/AsyncAPI + üretilen tipler), paylaşılan primitive'ler, observability, test altyapısı, config. |
| `infra/` | Docker container tanımları ve Alembic migration'ları. |
| `scripts/` | Fitness check, contract lint, secret scan gibi doğrulama script'leri. |
| `tests/` | Tek bir modülün sınırını aşan e2e ve güvenlik (cross-tenant, negatif authz) testleri. |
| `docs/` | Tek gerçek kaynak. Kod ile birlikte güncellenir. |

Her klasörün kendi `README.md`'si o klasörün **bağımlılık sınırını** açıklar. Bu sınırlar CI'da otomatik doğrulanacaktır ([dependency-rules.md](docs/architecture/dependency-rules.md), FF-01…FF-16).

---

## Bağımlılık yönü (özet)

```text
presentation ──┐
               ├──► application ──► domain   (domain hiçbir şeye bağımlı değil)
infrastructure ┘        │
                        └──► ports ◄── infrastructure IMPLEMENTE eder
```

- **Domain katmanı** FastAPI, SQLAlchemy, Pydantic, Next.js veya Supabase SDK'sına **bağımlı olamaz**.
- Bir modül başka modülün tablosuna **yazamaz**; command veya integration event kullanır.
- Provider entegrasyonları **yalnız adapter katmanında** bulunur.

---

## Kurulum

> **Henüz kurulacak bir şey yok.** Dependency, virtual environment, container ve scaffold **bilinçli olarak oluşturulmamıştır.**

Kurulum talimatları backend/frontend scaffold aşamasında bu bölüme eklenecektir. `.env.example` ileride hangi kategorilerde değişken gerekeceğini gösterir; **gerçek secret içermez**.

---

## Lisans

Özel (private). Tüm hakları saklıdır.
