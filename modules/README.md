# modules/ — Bounded Context'ler

İş mantığının yaşadığı yer. Modüler monolitin (ADR-003) kalbi burasıdır ve **en büyük risk buradaki sınırların erimesidir**. Aynı kod tabanında olmak, doğrudan import'u ve cross-module DB yazımını teknik olarak *kolay* kılar — bu yüzden sınırlar CI fitness function'larıyla zorlanır ([dependency-rules.md](../docs/architecture/dependency-rules.md)).

## MVP bounded context'leri (13)

| Modül | Sahip olduğu kavramlar | Sahip olduğu tablolar |
|---|---|---|
| [identity/](identity/README.md) | User, external auth binding | `users` |
| [organization/](organization/README.md) | Tenant, Membership, Team | `tenants`, `memberships`, `teams`, `team_members` |
| [authorization/](authorization/README.md) | Role, Permission, Policy | `roles`, `role_permissions` |
| [workflow-design/](workflow-design/README.md) | WorkflowDraft, WorkflowVersion, Form Schema | `workflows`, `workflow_versions`, `workflow_nodes`, `workflow_edges`, `form_schemas` |
| [workflow-runtime/](workflow-runtime/README.md) | WorkflowInstance, NodeExecution, Timer | `workflow_instances`, `node_executions`, `timers` |
| [work-management/](work-management/README.md) | Task, Assignment | `tasks`, `task_assignments` |
| [approval/](approval/README.md) | ApprovalRequest, Step, Decision | `approval_requests`, `approval_steps`, `approval_decisions` |
| [purchase-request/](purchase-request/README.md) | PurchaseRequest, FormSubmission | `purchase_requests`, `form_submissions` |
| [document/](document/README.md) | Document, DocumentLink | `documents`, `document_links` |
| [notification/](notification/README.md) | Notification | `notifications` |
| [audit/](audit/README.md) | AuditEvent (append-only) | `audit_events` |
| [analytics/](analytics/README.md) | Dashboard read model | read model / view |
| [platform/](platform/README.md) | Outbox, Inbox, Idempotency | `outbox_events`, `processed_events`, `idempotency_keys` |

MVP dışı (klasör **oluşturulmaz**): AI orchestration, integration/webhook, billing & entitlements.

## Modül iç yapısı

```text
<module>/
├── domain/          # entity, value object, policy, event, error — HİÇBİR ŞEYE bağımlı değil
├── application/     # command, query, handler, port — yalnız domain'e bağımlı
├── infrastructure/  # persistence (SQLAlchemy), provider adapter — portları IMPLEMENTE eder
├── presentation/    # http router, event consumer
└── tests/
```

Bağımlılık oku **her zaman içe doğrudur**. Domain dış katmanları bilmez.

## Sahiplik kuralı (bozulamaz)

- Bir tabloyu **yalnız sahibi olan modül yazar**.
- Cross-module **okuma** → sahibinin açık query contract'ı / read model'i.
- Cross-module **yazma** → sahibinin command API'si veya versiyonlu integration event'i.
- Bir modül başka modülün `infrastructure/persistence`'ını **import edemez**.
- İç domain event doğrudan modül sınırı dışına **yayınlanamaz**.

Örnek: Approval modülü `tasks` tablosuna **yazamaz**. Notification modülü `approval_steps`'i **okuyamaz** — ihtiyacı olan veriyi `approval.decided.v1` event payload'ından alır.

## Durum

Tüm modül klasörleri **boş**. Kaynak kodu henüz oluşturulmadı.
