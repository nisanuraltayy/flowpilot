# flowpilot.modules — Bounded Context'ler

İş mantığının yaşadığı yer. Modüler monolitin (ADR-003) kalbi burasıdır ve **en büyük risk buradaki sınırların erimesidir**. Aynı distribution içinde olmak, doğrudan import'u ve cross-module DB yazımını teknik olarak *kolay* kılar — bu yüzden sınırlar CI fitness function'larıyla zorlanır ([dependency-rules.md](../../../../../docs/architecture/dependency-rules.md)).

Import kökü ve fiziksel yerleşim kararı: [ADR-009](../../../../../docs/adr/ADR-009-python-physical-layout.md).

## MVP bounded context'leri (13)

| Import yolu | Sahip olduğu kavramlar | Sahip olduğu tablolar |
|---|---|---|
| [`flowpilot.modules.identity`](identity/README.md) | User, external auth binding | `users` |
| [`flowpilot.modules.organization`](organization/README.md) | Tenant, Membership, Team | `tenants`, `memberships`, `teams`, `team_members` |
| [`flowpilot.modules.authorization`](authorization/README.md) | Role, Permission, Policy | `roles`, `role_permissions` |
| [`flowpilot.modules.workflow_design`](workflow_design/README.md) | WorkflowDraft, WorkflowVersion, Form Schema | `workflows`, `workflow_versions`, `workflow_nodes`, `workflow_edges`, `form_schemas` |
| [`flowpilot.modules.workflow_runtime`](workflow_runtime/README.md) | WorkflowInstance, NodeExecution, Timer | `workflow_instances`, `node_executions`, `timers` |
| [`flowpilot.modules.work_management`](work_management/README.md) | Task, Assignment | `tasks`, `task_assignments` |
| [`flowpilot.modules.approval`](approval/README.md) | ApprovalRequest, Step, Decision | `approval_requests`, `approval_steps`, `approval_decisions` |
| [`flowpilot.modules.purchase_request`](purchase_request/README.md) | PurchaseRequest, FormSubmission | `purchase_requests`, `form_submissions` |
| [`flowpilot.modules.document`](document/README.md) | Document, DocumentLink | `documents`, `document_links` |
| [`flowpilot.modules.notification`](notification/README.md) | Notification | `notifications` |
| [`flowpilot.modules.audit`](audit/README.md) | AuditEvent (append-only) | `audit_events` |
| [`flowpilot.modules.analytics`](analytics/README.md) | Dashboard read model | read model / view |
| [`flowpilot.modules.platform`](platform/README.md) | Outbox, Inbox, Idempotency | `outbox_events`, `processed_events`, `idempotency_keys` |

MVP dışı (paket **oluşturulmaz**): AI orchestration, integration/webhook, billing & entitlements.

## Adlandırma kuralı

Bounded context klasör adları **snake_case** olmalıdır — bunlar doğrudan Python import yoludur.
**Tireli ad YASAK:** `import flowpilot.modules.workflow-runtime` bir **syntax hatasıdır** ve statik analizi, IDE'yi, mypy'ı ve fitness function'ları kör eder.

## Modül iç yapısı

```text
flowpilot/modules/<context>/
├── domain/          # entity, value object, policy, event, error — HİÇBİR ŞEYE bağımlı değil
├── application/     # command, query, handler, port
├── infrastructure/  # persistence (SQLAlchemy), provider adapter — portları IMPLEMENTE eder
└── presentation/    # http router, event consumer
```

Bağımlılık oku **her zaman içe doğrudur**. Domain dış katmanları bilmez.

**Testler burada DEĞİL**, `apps/backend/tests/` altındadır (ADR-009).

## Import kuralları (bozulamaz)

```python
# ✅ domain — yalnız kendi domain'i ve shared primitive'ler
from flowpilot.shared.money import Money
from flowpilot.modules.approval.domain.approval_step import ApprovalStep  # kendi modülü içinde

# ❌ domain katmanında framework / ORM / provider SDK
from sqlalchemy import Column  # YASAK
from fastapi import Depends  # YASAK

# ❌ başka bir context'in domain veya infrastructure katmanı
from flowpilot.modules.approval.infrastructure.models import ApprovalStepRow  # YASAK
from flowpilot.modules.approval.domain.approval_step import ApprovalStep  # başka modülden YASAK
```

- Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
- Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden yapılır.
- **`PYTHONPATH` hack'i kullanılmaz**; paket editable install ile çözülür.
- **Aynı bounded context için ikinci bir source of truth oluşturulmaz.**

## Sahiplik kuralı (bozulamaz)

- Bir tabloyu **yalnız sahibi olan modül yazar**.
- Cross-module **okuma** → sahibinin açık query contract'ı / read model'i.
- Cross-module **yazma** → sahibinin command API'si veya versiyonlu integration event'i.
- İç domain event doğrudan modül sınırı dışına **yayınlanamaz**.

Örnek: Approval modülü `tasks` tablosuna **yazamaz**. Notification modülü `approval_steps`'i **okuyamaz** — ihtiyacı olan veriyi `approval.decided.v1` event payload'ından alır.

## Durum

Tüm modül paketleri **boş**. Kaynak kodu ve `__init__.py` henüz oluşturulmadı.
