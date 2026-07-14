# CLAUDE.md — FlowPilot Günlük Geliştirme Talimatı

> Bu dosya kısa tutulur. Detay kurallar `.claude/rules/` altındadır. PRD buraya kopyalanmaz.

## 1. Proje amacı

FlowPilot; KOBİ'ler için çok kiracılı (multi-tenant) bir iş akışı, talep ve onay platformudur. Ürünün değeri görev listelemek değil; **talepleri kurala göre yönlendirmek, onayları deterministik yürütmek ve her kritik işlemi denetlenebilir kılmaktır**.

**Bu repository Career Copilot'tan tamamen bağımsızdır.** Career Copilot klasörüne, dosyalarına veya veritabanına hiçbir koşulda dokunma; oradan kod, şema veya konfigürasyon kopyalama.

Çalışma modeli: solo developer + AI coding agent. Mimari: modüler monolit. Repository: monorepo.

## 2. Kaynakların okunma sırası

Bir çatışma olduğunda **üstteki kazanır**. Mevcut kod bu sıranın üstündeki bir kaynakla çelişiyorsa mevcut kod "doğru" kabul edilmez; çelişki ADR veya open question olarak görünür hâle getirilir.

1. Güvenlik, tenant izolasyonu ve hukuki zorunluluklar
2. Kabul edilmiş ADR kayıtları — [docs/adr/](docs/adr/README.md)
3. PRD içindeki MUST / MUST NOT kuralları — [docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md](docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md)
4. API ve event sözleşmeleri
5. Domain invariant'ları ve state machine kuralları (PRD §36)
6. Story kabul kriterleri — [docs/backlog/](docs/backlog/epics.yaml)
7. `.claude/rules/*` ve kod standartları
8. Mevcut implementasyon
9. Agent varsayımları — [docs/assumptions.md](docs/assumptions.md)

## 3. Aktif mimari kararlar

| ADR | Karar | Durum |
|---|---|---|
| [ADR-001](docs/adr/ADR-001-backend-stack.md) | Backend: Python + FastAPI + Pydantic + SQLAlchemy + Alembic | Accepted |
| [ADR-002](docs/adr/ADR-002-frontend-stack.md) | Frontend: Next.js + TypeScript | Accepted |
| [ADR-003](docs/adr/ADR-003-modular-monolith.md) | Modüler monolit + arka plan worker'ları | Accepted |
| [ADR-004](docs/adr/ADR-004-workflow-runtime-spike.md) | `WorkflowRuntimePort` arkasında custom PostgreSQL-backed runtime; **önce spike**. Camunda 8 elendi, Temporal yedek | Accepted (koşullu) |
| [ADR-005](docs/adr/ADR-005-authentication-boundary.md) | **Supabase Auth** — yalnız authentication. Org/membership/RBAC/tenant FlowPilot domain'inde ve FlowPilot'ın PostgreSQL'inde. Domain, Supabase SDK'sına bağımlı olamaz | Accepted |
| [ADR-006](docs/adr/ADR-006-postgresql-tenant-isolation.md) | Application-level tenant scope + PostgreSQL RLS (defense-in-depth) | Accepted |
| [ADR-007](docs/adr/ADR-007-transactional-outbox.md) | Transactional outbox + PostgreSQL-backed polling worker | Accepted |
| [ADR-008](docs/adr/ADR-008-monorepo.md) | Monorepo | Accepted |
| [ADR-009](docs/adr/ADR-009-python-physical-layout.md) | **Tek Python distribution** (`flowpilot-backend`, `apps/backend`), tek import kökü `flowpilot`. Bounded context'ler `flowpilot.modules.<snake_case>`. `api` ve `worker` aynı paketin iki composition root'u | Accepted |

Diğer kesinleşmiş kararlar: PostgreSQL tek source of truth · S3-compatible storage portu (local: MinIO adayı) · Arama MVP'de PostgreSQL full-text · Deployment Docker tabanlı ve provider-neutral (ilk aday Render) · AI özellikleri ve workflow builder canvas gerçek MVP dışında.

**Gerçek MVP node seti:** Start, Form, Condition, Sequential Approval, Notification, End. Bunun dışındaki hiçbir node tipi (parallel split/join, quorum, sub-workflow, webhook, script, AI, DMN) implemente edilmez.

### Kapsam kaynağı

> **Teslim edilecek kapsam için bağlayıcı doküman: [docs/product/mvp-scope-v0.1.md](docs/product/mvp-scope-v0.1.md)** (owner-approved).
> Bu doküman, PRD §7.1 ve §24'teki geniş MVP tanımının **üzerinde** önceliğe sahiptir. PRD değiştirilmez; araştırma ve uzun vadeli vizyon olarak korunur. PRD'nin **mühendislik kuralları** (invariant, anti-pattern, state machine, güvenlik) tam olarak bağlayıcıdır.

E-posta bildirimi ve gerçek malware taraması **pilot-ready** kapsamındadır (MVP dışı); ancak `NotificationChannelPort` ve `MalwareScanPort` **şimdiden** provider-neutral tasarlanır — sonradan eklemek bir adapter işi olmalı, refactor değil.

## 4. Karar kilitleri

Kilit açıkken agent o kararı üretim kodunda **varsayamaz**. Yalnızca karşılaştırma, spike, ADR ve port sözleşmesi üretebilir.

| Kilit | Konu | Durum | Agent davranışı |
|---|---|---|---|
| LOCK-001 | Backend stack | **KAPALI** (ADR-001) | Karara göre ilerle |
| LOCK-002 | Frontend stack | **KAPALI** (ADR-002) | Karara göre ilerle |
| LOCK-003 | Workflow runtime | **KOŞULLU** (ADR-004) | Spike exit criteria geçmeden runtime'a bağlı üretim kodu yazma |
| LOCK-004 | Auth provider | **KAPALI** (ADR-005 — Supabase Auth) | Supabase yalnız `AuthProviderPort` adapter'ı içinde. Domain SDK'ya bağımlı olamaz. Entegrasyon bootstrap onayından sonra |
| LOCK-005 | Queue/worker altyapısı | **KAPALI** (ADR-007) | Outbox + PostgreSQL polling worker |
| LOCK-006 | Hosting / veri bölgesi | **AÇIK** | Deployment provider-neutral kalır |
| LOCK-007 | AI provider ve veri politikası | **AÇIK** | MVP dışı. Gerçek AI entegrasyonu yok |
| LOCK-008 | Monorepo / polyrepo | **KAPALI** (ADR-008) | Monorepo |

## 5. Yasaklanan davranışlar

- Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu.
- Bir bounded context'in başka bir context'in `domain` veya `infrastructure` katmanını doğrudan import etmesi.
- `flowpilot.api` / `flowpilot.worker` içinde iş mantığı; composition root dışında adapter wiring.
- `PYTHONPATH` hack'i; tireli (snake_case olmayan) Python paket adı.
- Aynı bounded context için ikinci bir source of truth.
- Bir modülün başka modülün tablosuna doğrudan yazması.
- Generic repository. Aggregate-specific repository kullan.
- Business logic'i controller veya frontend içine gömmek.
- Published workflow version'ı değiştirmek.
- Parayı float olarak tutmak. `minor_unit + currency` kullan.
- Naive datetime. Her şey UTC saklanır.
- Tenant verisini `tenant_id` olmadan modellemek; tenant filtresini geliştiricinin hatırlamasına bırakmak.
- Kullanıcı koşullarında `eval` veya dinamik Python/JavaScript çalıştırmak.
- Audit log'u application log yerine (veya tersi) kullanmak.
- Sonsuz retry.
- Failing test'i silmek, `skip`/`xfail` ile geçmek veya beklentiyi implementasyona uydurmak.
- Güvenlik kontrolünü kapatmak; `--no-verify` kullanmak.
- Secret, kişisel veri veya production credential commit etmek.
- Bilinmeyen gereksinimi uydurmak; TODO/fake success ile "tamamlandı" demek.
- Career Copilot klasörüne dokunmak.

Genişletilmiş liste: [.claude/rules/architecture.md](.claude/rules/architecture.md) ve [.claude/rules/security.md](.claude/rules/security.md).

## 6. Çalıştırılması zorunlu kalite kontrolleri

> **Şu an:** Repository bootstrap henüz onaylanmadı. Kod, dependency ve komut bulunmuyor. Bu bölümdeki kapılar bootstrap (Epic E00) tamamlandığında zorunlu hâle gelir. **Var olmayan komutu uydurma ve çalıştırma.**

Bootstrap sonrasında her story için zorunlu kapılar:

| Kapı | Kapsam |
|---|---|
| Format + lint | Backend ve frontend |
| Type check | Python type check + TypeScript |
| Unit test | Domain, policy, evaluator, state machine |
| Integration test | DB transaction, outbox, worker, storage portu |
| Contract test | OpenAPI/AsyncAPI lint + breaking-change diff |
| Cross-tenant test | Tenant verisine dokunan her story'de zorunlu |
| Negative authorization test | Yetki kontrolü olan her endpoint'te zorunlu |
| Migration test | Boş DB + bir önceki release şeması üzerinde |
| Secret scan | Her commit |

Bu kapıların tümü geçmeden story **done** sayılmaz.

## 7. Story çalışma protokolü

1. İlgili **PRD bölümünü** oku.
2. **Aktif ADR'leri** oku.
3. **Story dosyasını** oku ([docs/backlog/](docs/backlog/vertical-slice-purchase-request.yaml)).
4. **Karar kilidi** var mı kontrol et. Varsa üretim kodu yazma; spike/ADR üret.
5. Büyük değişiklikten önce **plan** üret.
6. **Bir story dışına taşma.**
7. Bir pull request'te **tek ana amaç** uygula.
8. API, event veya migration değiştiyse **sözleşmeleri güncelle**.
9. Tenant verisi kullanan kod için **cross-tenant test** yaz.
10. Authorization için **negatif test** yaz.
11. Test, lint ve type-check geçmeden story'yi **tamamlanmış sayma**.
12. Güvenlik kontrolünü **kapatma**.
13. Bilinmeyen gereksinimi **uydurma**.
14. Varsayımı **ASM-xxxx** kimliğiyle [docs/assumptions.md](docs/assumptions.md) içine yaz.
15. Owner kararı gerektiren konuyu **OQ-xxx** kimliğiyle [docs/open-questions.md](docs/open-questions.md) içine yaz.
16. Secret veya kişisel veri **commit etme**.

Ayrıntılı protokol ve teslim raporu formatı: [AGENTS.md](AGENTS.md).

## 8. Kural dosyaları

- [.claude/rules/architecture.md](.claude/rules/architecture.md) — modül sınırları, port/adapter, bağımlılık yönü, anti-pattern'ler
- [.claude/rules/security.md](.claude/rules/security.md) — tenant izolasyonu, authorization, audit, secret, koşul değerlendirme
- [.claude/rules/testing.md](.claude/rules/testing.md) — test piramidi, zorunlu test türleri, coverage hedefleri
- [.claude/rules/database.md](.claude/rules/database.md) — şema, migration, JSONB, para/zaman, RLS, index
- [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) — branch, commit, PR, diff sınırı, review checklist
