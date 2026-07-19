# Mimari Kuralları

Bağlayıcı kaynak: PRD §11, §35, §38, §39 ve kabul edilmiş ADR'ler ([ADR-003](../../docs/adr/ADR-003-modular-monolith.md), [ADR-009](../../docs/adr/ADR-009-python-physical-layout.md)).

## 0. Fiziksel yerleşim (ADR-009)

Tek Python distribution: **`flowpilot-backend`** (`apps/backend`), tek import kökü **`flowpilot`**.

```text
apps/backend/src/flowpilot/
├── shared/ observability/ config/       # ayrı distribution DEĞİL
├── modules/<snake_case>/                # 13 bounded context
│   └── domain/ application/ infrastructure/ presentation/
├── api/                                 # composition root — İŞ MANTIĞI YOK
└── worker/                              # composition root — İŞ MANTIĞI YOK
```

Bounded context klasör adları **snake_case**'dir; tireli ad Python import yolunda **kullanılamaz**.

## 1. Katman ve bağımlılık yönü

```
presentation (FastAPI router / event consumer)
      ↓
application (command, query, handler, port)
      ↓
domain (entity, value object, policy, event, error)
      ↑
infrastructure (persistence, messaging, provider adapter) — portları IMPLEMENTE eder
```

**MUST NOT:**

- **Domain katmanında FastAPI, SQLAlchemy, Supabase veya herhangi bir provider SDK importu YASAK:**
  ```python
  # flowpilot/modules/approval/domain/*.py içinde:
  from sqlalchemy import Column     # YASAK
  from fastapi import Depends       # YASAK
  ```
- Infrastructure tipleri (ORM modeli, SDK response objesi, HTTP request objesi) domain'e sızamaz.
- Application katmanı somut adapter'a değil, **porta** bağımlıdır.

**MUST:**

- Domain, ihtiyaç duyduğu her dış yeteneği bir **port** (protocol/interface) olarak tanımlar; infrastructure bu portu uygular.
- Zaman `ClockPort` ile alınır; domain içinde doğrudan sistem saati okunmaz.
- ID üretimi injectable generator üzerinden yapılır; domain içinde doğrudan random ID üretilmez.

## 2. Modül sınırları

Bounded context'ler (snake_case): `identity`, `organization`, `authorization`, `workflow_design`, `workflow_runtime`, `work_management`, `approval`, `purchase_request`, `document`, `notification`, `audit`, `analytics`, `platform`.

**MUST NOT:**

- Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**:
  ```python
  # flowpilot/modules/notification/... içinde:
  from flowpilot.modules.approval.infrastructure.models import ApprovalStepRow   # YASAK
  from flowpilot.modules.approval.domain.approval_step import ApprovalStep       # YASAK
  ```
- Bir modül başka bir modülün tablosuna **doğrudan yazamaz**.
- `flowpilot.shared` domain çöplüğüne dönüşemez. İçinde yalnız primitive, error base, ID, `ClockPort` ve telemetry sözleşmeleri bulunur.
- **`PYTHONPATH` hack'i YASAK** — paket editable install ile çözülür (`pip install -e apps/backend`).
- **Aynı bounded context için ikinci bir source of truth oluşturulamaz.**

**MUST:**

- Cross-module **okuma**: açık application contract veya read model üzerinden.
- Cross-module **yazma**: command API veya versiyonlu integration event üzerinden.
- İç domain event'i doğrudan modül sınırı dışına yayınlanmaz; versiyonlu integration event'e dönüştürülür.

## 2b. Composition root sınırı

`flowpilot.api` ve `flowpilot.worker` — **ayrı Python projeleri değil**, aynı distribution'ın iki entrypoint'i. İkisi de aynı domain/application kodunu kullanır.

**MUST NOT:** İçlerinde iş mantığı bulunamaz (yetki kararı, koşul değerlendirmesi, onay sırası, state transition).
**MUST:** Yalnız `flowpilot.modules.*.application` sınırlarını çağırırlar. **Adapter wiring yalnız burada** yapılır (`api/deps.py`, `worker/wiring.py`).

## 3. Port / adapter zorunluluğu

Aşağıdakiler **yalnızca** port arkasında kullanılır:

| Port | MVP adayı |
|---|---|
| `AuthProviderPort` | Supabase Auth / Clerk — **karar açık (ADR-005)**; şimdilik fake adapter |
| `WorkflowRuntimePort` | Custom PostgreSQL-backed runtime — **spike 12/12 geçti; ADR-004 Accepted, LOCK-003 kapandı (2026-07-19)** |
| `FileStoragePort` | S3-compatible; local development için MinIO adayı |
| `NotificationChannelPort` | MVP'de yalnız in-app kanal |
| `ClockPort` | Testte fake clock |
| `IdGeneratorPort` | UUID/ULID |

Provider SDK nesneleri adapter katmanının dışına çıkamaz. Testler fake/in-memory adapter kullanabilir; ancak bir story yalnızca mock'a karşı test edilerek "done" sayılamaz.

## 4. Repository kuralı

- **YASAK:** Generic repository (`Repository<T>`, `BaseRepository.get_all()` vb.).
- **ZORUNLU:** Aggregate-specific repository veya query object. Örnek: `WorkflowDraftRepository`, `ApprovalRequestRepository`, `TaskInboxQuery`.
- Repository, aggregate sınırını korur; tek dev aggregate içinde tüm workflow instance grafiği yüklenmez.

Aggregate'lar: `WorkflowDraft`, `WorkflowVersion`, `WorkflowInstance`, `Task`, `ApprovalRequest`, `OrganizationMembership`, `PurchaseRequest`.

## 5. Business logic'in yeri

- Business logic **domain/application** katmanındadır.
- **YASAK:** Controller/router içinde iş kuralı; frontend'de yetki veya routing kararı.
- **YASAK:** Dağınık `if role == "admin"` kontrolleri. Authorization merkezi policy boundary'sindedir.
- State geçişleri servislerde dağınık `if` blokları ile değil, merkezi **transition policy** ile yönetilir.
- Authorization, self-approval kontrolü, assignment stratejisi, form görünürlüğü ve condition evaluator **policy/specification objesi** olarak test edilebilir tutulur.

## 6. Workflow tanımı

- **Published workflow version IMMUTABLE'dır.** Yayınlanan içerik hash'lenir; üzerine update sorgusu çalıştıran kod bulunamaz.
- Her instance **tam olarak bir** published version'a bağlıdır.
- Yeni düzenleme yeni draft üretir; published kayıt değişmez.
- Terminal instance yeni node başlatamaz.
- Bilinmeyen node tipi yayınlanamaz.

**MVP node seti:** `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`. Başka node tipi implemente edilmez.

## 7. Asenkron işlem

- Domain state değişikliği ve integration event **aynı transaction'da** outbox tablosuna yazılır (transactional outbox).
- Dual write (DB commit + ayrı event publish) **YASAK**.
- Consumer idempotenttir; işlediği message kimliğini kaydeder (idempotent inbox).
- "Exactly once" iddiası **YASAK**. Yaklaşım: at-least-once delivery + idempotent consumer.
- Timer'lar **veritabanında** tutulur. In-memory timer ve web process içinde cron **YASAK**.
- Retry: yalnız geçici hatalarda, exponential backoff + jitter, maksimum attempt ve maksimum toplam süre ile. **Sonsuz retry YASAK.** Validation/authorization/kalıcı business error retry edilmez.

## 8. Eşzamanlılık

Optimistic concurrency (`version` alanı / ETag) zorunlu kaynaklar:

- Workflow draft
- Task assignment ve state
- Approval step
- Organization settings
- Purchase request (revizyon sırasında)

Stale write `409 Conflict` veya `412 Precondition Failed` döner. "Son yazan kazanır" kritik kaynaklarda **YASAK**.

## 9. Yasaklı anti-pattern'ler

| Anti-pattern | Doğru yaklaşım |
|---|---|
| Premature microservices | Modüler monolit; ölçüm sonrası extraction |
| Event sourcing everywhere | Append-only audit + normal state + domain events |
| Generic JSON blob domain | Stabil alanları normalize et; esnek config'i şemalı JSONB'de tut |
| Published workflow mutation | Immutable version |
| Dual write | Transactional outbox |
| Business logic in frontend | Server-side domain policy |
| Role check scattering | Merkezi authorization policy |
| God service (`WorkflowService`) | Use-case ve bounded context ayrımı |
| Generic repository | Aggregate-specific repository |
| Direct cross-module DB write | Command/event contract |
| In-memory timer | Persisted timer + worker |
| Cron inside web process | Dedicated worker |
| Infinite retry | Bounded retry + DLQ/incident |
| Runtime `eval` | Güvenli DSL + parser |
| Money as float | Minor unit + currency |
| Naive datetime | UTC + explicit timezone |
| Cache without tenant key | Tenant-scoped cache key |
| Provider SDK in domain | Port/adapter |
| Optimistic UI for approval | Server-confirmed state |
| Unbounded list endpoint | Cursor pagination + max page size |
| Disabling tests to merge | Root cause fix veya açık risk acceptance |
| One giant autonomous PR | Tek story / vertical slice |

## 10. Mimari fitness function'ları

CI (Epic E00 sonrası) şunları otomatik doğrular:

1. Domain paketleri infrastructure paketlerini import etmez.
2. Modül A'nın persistence modeli modül B tarafından import edilmez.
3. Tenant'a ait her tablo `tenant_id` içerir veya açık global-data istisnasına sahiptir.
4. Mutasyona açık her aggregate optimistic concurrency alanına sahiptir.
5. Her public endpoint bir authorization policy adı belirtir.
6. Her background handler idempotency davranışını tanımlar.
7. Domain içinde doğrudan sistem saati kullanılmaz.
8. Published workflow verisine `UPDATE` çalıştıran kod bulunmaz.
9. Domain içinde `eval`/`exec` bulunmaz.
