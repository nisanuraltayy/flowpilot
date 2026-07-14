# Dependency Rules — Bağımlılık Kuralları ve Fitness Function'ları

Bağlayıcı kaynak: PRD §35.2, §35.3, §38, §39. İlgili ADR: [ADR-001](../adr/ADR-001-backend-stack.md), [ADR-003](../adr/ADR-003-modular-monolith.md), [ADR-008](../adr/ADR-008-monorepo.md), **[ADR-009](../adr/ADR-009-python-physical-layout.md)**.

Bu kurallar **öneri değildir**. CI'da otomatik doğrulanır (bootstrap sonrası); ihlal eden PR merge edilemez.

---

## 0. Fiziksel yerleşim ve import kökü (ADR-009)

Tek Python distribution: **`flowpilot-backend`** (`apps/backend`), tek import kökü **`flowpilot`**.

```text
apps/backend/src/flowpilot/
├── shared/           # flowpilot.shared          — primitive'ler, ClockPort, IdGeneratorPort
├── observability/    # flowpilot.observability
├── config/           # flowpilot.config
├── modules/          # flowpilot.modules.<snake_case>  — 13 bounded context
├── api/              # flowpilot.api      — composition root
└── worker/           # flowpilot.worker   — composition root
```

**Bağlayıcı import kuralları:**

1. **Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK.**
2. Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır.
5. **Adapter wiring yalnız composition root'ta** (`api/deps.py`, `worker/wiring.py`).
6. **`PYTHONPATH` hack'i YASAK** — editable install (`pip install -e apps/backend`).
7. Bounded context klasör adları **snake_case**; tireli ad YASAK (`import flowpilot.modules.workflow-runtime` bir syntax hatasıdır).
8. **Aynı bounded context için ikinci source of truth YASAK.**

---

## 1. Katman bağımlılığı

```
      presentation                infrastructure
   (FastAPI / Next.js)     (SQLAlchemy, S3, provider SDK)
            │                          │
            │  bağımlı                 │  IMPLEMENTE eder
            ▼                          ▼
       application  ────tanımlar───►  ports
            │
            │  bağımlı
            ▼
         domain          (hiçbir şeye bağımlı değil)
```

**Bağımlılık oku her zaman içe doğrudur.** Domain hiçbir dış katmanı bilmez.

| Katman | Bağımlı olabilir | Bağımlı OLAMAZ |
|---|---|---|
| `domain` | Yalnız standart kütüphane ve `shared` primitive'ler | FastAPI, SQLAlchemy, Pydantic, Next.js, herhangi bir provider SDK, başka modülün domain'i |
| `application` | Kendi domain'i, kendi port'ları, `shared` | Somut adapter, ORM modeli, HTTP framework |
| `infrastructure` | `application` port'ları, kendi domain'i, dış SDK'lar | Başka modülün domain veya persistence'ı |
| `presentation` | `application` (command/query) | Doğrudan repository, doğrudan domain mutasyonu |

### Yasak import örnekleri

```python
# flowpilot/modules/approval/domain/*.py içinde
from sqlalchemy import Column                                              # ❌
from fastapi import Depends                                                # ❌
from supabase import create_client                                         # ❌

# flowpilot/modules/notification/*.py içinde  (cross-context)
from flowpilot.modules.approval.infrastructure.models import ApprovalRow   # ❌
from flowpilot.modules.approval.domain.approval_step import ApprovalStep   # ❌

# flowpilot/api/routers/*.py içinde  (composition root)
from flowpilot.modules.approval.infrastructure.repository import ...       # ❌ (wiring hariç)
from flowpilot.modules.approval.domain.policies import ...                 # ❌

# apps/web (TypeScript)
import ... from "../../apps/backend/..."                                   # ❌ sözleşme üzerinden konuşur
```

### İzin verilen import örnekleri

```python
# composition root → application sınırı
from flowpilot.modules.approval.application.commands import DecideApprovalStep

# domain → shared primitive
from flowpilot.shared.money import Money
from flowpilot.shared.clock import ClockPort

# infrastructure → kendi application port'u + dış SDK
from flowpilot.modules.approval.application.ports import ApprovalRepository
from sqlalchemy.orm import Session
```

---

## 2. Modüller arası bağımlılık

**MUST NOT:**

1. Bir modül başka modülün **tablosuna yazamaz**.
2. Bir modül başka modülün **persistence modelini import edemez**.
3. Bir modülün domain'i başka modülün domain'ini import edemez.
4. İç domain event doğrudan modül sınırı dışına yayınlanamaz.

**MUST:**

- Cross-module **okuma** → sahibinin açık query contract'ı / read model'i.
- Cross-module **yazma** → sahibinin command API'si veya versiyonlu integration event.
- Integration event `tenant_id`, `correlation_id` ve versiyonlu `type` (`approval.decided.v1`) taşır.

### İzin verilen bağımlılık yönü (MVP)

```mermaid
flowchart TD
    IDENTITY[identity] --> SHARED[shared]
    ORG[organization] --> IDENTITY
    AUTHZ[authorization] --> ORG
    WFDESIGN[workflow_design] --> AUTHZ
    WFRUNTIME[workflow_runtime] --> WFDESIGN
    APPROVAL[approval] --> AUTHZ
    WORK[work_management] --> AUTHZ
    PURCHASE[purchase_request] --> WFDESIGN
    DOC[document] --> AUTHZ
    NOTIFY[notification] --> SHARED
    AUDIT[audit] --> SHARED
    ANALYTICS[analytics] --> SHARED
```

- `workflow_runtime`, `approval` ve `work_management`'a **event/komut üzerinden** ulaşır — doğrudan import ile değil.
- `notification`, `audit` ve `analytics` **hiçbir iş modülünü import etmez**; yalnız event tüketir. Bu, onları ileride servis olarak ayırmayı mümkün kılar (ADR-009 §Future service extraction).
- `flowpilot.shared` **hiçbir bounded context'e bağımlı değildir**.

---

## 3. `flowpilot.shared` paketi kuralı

`flowpilot.shared` yalnızca şunları barındırır:

- Primitive value object'ler (`Money`, `TenantId`, `UserId`, `Ulid`)
- Error base sınıfları ve error catalog sözleşmesi
- `Clock` port'u
- `IdGenerator` port'u
- Telemetry (log/metric/trace) sözleşmeleri

**YASAK:** İş kuralı, entity, use case, repository, "yardımcı" fonksiyon çöplüğü. `flowpilot.shared` bir domain modülü değildir.

> `shared`, `observability` ve `config` **ayrı Python distribution DEĞİLDİR** — `flowpilot`'ın alt paketleridir (ADR-009).

---

## 4. Port ve adapter

Dış dünyaya açılan her yetenek port arkasındadır:

| Port | Katman | MVP adapter'ı |
|---|---|---|
| `AuthProviderPort` | `flowpilot.modules.identity.application` | **Supabase adapter** + fake adapter (ADR-005) |
| `WorkflowRuntimePort` | `flowpilot.modules.workflow_runtime.application` | Custom PostgreSQL-backed runtime (**spike şartına bağlı** — ADR-004) |
| `FileStoragePort` | `flowpilot.modules.document.application` | S3-compatible; local development MinIO adayı |
| `MalwareScanPort` | `flowpilot.modules.document.application` | MVP'de yalnız no-op/stub (gerçek tarama: pilot-ready) |
| `NotificationChannelPort` | `flowpilot.modules.notification.application` | In-app kanal (kanal-nötr port; e-posta pilot-ready) |
| `ClockPort` | `flowpilot.shared` | System clock / fake clock |
| `IdGeneratorPort` | `flowpilot.shared` | ULID generator |

**Kurallar:**

- Provider SDK nesneleri adapter'ın **dışına çıkamaz** (anti-corruption layer).
- Fake adapter ve gerçek adapter **aynı contract test setini** geçer.
- Bir story yalnızca fake adapter'a karşı test edilerek "done" sayılamaz; gerçek boundary (DB, transaction, worker) en az bir integration testte doğrulanır.

---

## 5. Frontend bağımlılık kuralı

- `apps/web` backend modüllerini **import etmez**. Yalnız `packages/contracts` üzerinden konuşur.
- API tipleri OpenAPI'den **üretilir**; elle yazılmaz.
- Frontend'de business logic bulunamaz: yetki kararı, koşul değerlendirmesi, onay sırası, SLA hesabı **yalnız** backend'dedir.
- Onay/ret kararlarında optimistic UI YASAK; server-confirmed state gösterilir.

---

## 6. Fitness function'ları (CI'da otomatik)

Bootstrap (Epic E00) sonrasında CI aşağıdakileri doğrular. Herhangi biri kırmızıysa **merge yok**.

| # | Kontrol | Başarısızlık anlamı |
|---|---|---|
| FF-01 | `flowpilot/modules/*/domain/**` içinde `sqlalchemy`, `fastapi`, `supabase` veya provider SDK importu yok | Katman ihlali |
| FF-02 | `flowpilot.modules.X.*` içinde `flowpilot.modules.Y.domain` veya `.infrastructure` importu yok (X ≠ Y) | Sahiplik ihlali |
| FF-02b | `flowpilot.api` / `flowpilot.worker` içinde `flowpilot.modules.*.domain` veya `.infrastructure` importu yok (wiring dosyaları hariç) | İş mantığı composition root'a sızmış |
| FF-02c | Bounded context klasör adları snake_case; tireli ad yok | Python import yolu geçersiz |
| FF-03 | Tenant verisi taşıyan her tabloda `tenant_id` var (whitelist dışında) | Tenant izolasyon riski |
| FF-04 | Tenant verisi taşıyan her tabloda RLS politikası tanımlı | Tenant izolasyon riski |
| FF-05 | Mutasyona açık her aggregate'te optimistic concurrency alanı var | Yarış koşulu riski |
| FF-06 | Her public endpoint bir authorization policy adı belirtiyor | Yetkisiz erişim riski |
| FF-07 | Her background handler idempotency davranışını tanımlıyor | Duplicate side effect riski |
| FF-08 | Kod tabanında `eval(`/`exec(` yok | Kod çalıştırma açığı |
| FF-09 | Para alanlarında `float`/`double` yok | Yuvarlama hatası |
| FF-10 | Naive datetime yok; tüm timestamp'ler timezone-aware (UTC) | Zaman hatası |
| FF-11 | Published workflow tablolarına `UPDATE` çalıştıran kod yok | Immutability ihlali |
| FF-12 | `domain/**` içinde doğrudan sistem saati okuması yok (`Clock` kullanılıyor) | Test edilemezlik |
| FF-13 | Her dış HTTP çağrısında timeout ve bounded retry var | Sonsuz retry / kaynak tüketimi |
| FF-14 | Her yeni permission merkezi katalogda kayıtlı | Dağınık yetki modeli |
| FF-15 | Her liste endpoint'i cursor pagination + max page size kullanıyor | DoS riski |
| FF-16 | MVP node seti dışında node tipi tanımlı değil | Scope creep |

---

## 7. Dependency ekleme politikası

Yeni bir dependency ekleyen PR şunları belgelemek zorundadır (PRD §46.3):

- Kullanım gerekçesi (standart kütüphane veya mevcut dependency neden yetmiyor?)
- Lisans
- Bakım durumu (son release, açık kritik issue)
- Güvenlik durumu (bilinen CVE)
- Bundle/runtime etkisi
- Değerlendirilen alternatifler
- Kaldırma maliyeti (removal cost)

Agent, **dependency eklemeden önce** standart kütüphaneyi ve mevcut dependency'leri kontrol eder. Gerekçesiz dependency merge edilemez.
