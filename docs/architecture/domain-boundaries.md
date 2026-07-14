# Domain Boundaries — Bounded Context Haritası

Bağlayıcı kaynak: PRD §11.3, §34, §35.1, §36. İlgili ADR: [ADR-003](../adr/ADR-003-modular-monolith.md) (modüler monolit), [ADR-006](../adr/ADR-006-postgresql-tenant-isolation.md) (tenant izolasyonu), [ADR-009](../adr/ADR-009-python-physical-layout.md) (fiziksel yerleşim).

Bu doküman **modül sahipliğini** tanımlar: hangi kavram hangi modüle aittir, hangi tabloyu kim yazar, modüller birbirine ne sunar.

**Fiziksel konum:** Tüm bounded context'ler `apps/backend/src/flowpilot/modules/<snake_case>/` altındadır; import yolu `flowpilot.modules.<snake_case>`. Klasör adları **snake_case**'dir — tireli ad Python import yolunda kullanılamaz.

---

## 1. Ubiquitous language (kritik ayrımlar)

Aşağıdaki terimler kodda **birbirinin yerine kullanılamaz**:

| Terim | Tanım | Karıştırılmaması gereken |
|---|---|---|
| **Tenant / Organization** | Veri ve yetki sınırı olan FlowPilot müşterisi | Workspace, company, account rastgele kullanılamaz |
| **Membership** | Kullanıcının bir tenant içindeki üyeliği ve rolü | Rol global user'a yazılamaz |
| **Workflow** | Mantıksal süreç ailesi | Instance değildir |
| **Workflow Draft** | Düzenlenebilir, yayınlanmamış tanım | Üzerinde instance başlatılamaz |
| **Workflow Version** | Yayınlanmış, **immutable** tanım | Draft değildir |
| **Workflow Instance** | Bir version'ın tek çalışması | Purchase request kaydı tek başına instance değildir |
| **Node Definition** | Tasarımdaki düğüm | Node execution değildir |
| **Node Execution** | Bir instance içindeki düğüm çalışma kaydı | Node definition değildir |
| **Human Task** | İnsan aksiyonu bekleyen iş | Approval her zaman task değildir; approval'ın kendi karar semantiği vardır |
| **Approval Request** | Onay düğümünün üst seviye talebi | Tek bir onaycının kararı değildir |
| **Approval Step** | Sıradaki tek onay adımı | Decision değildir |
| **Approval Decision** | Bir yetkilinin verdiği **immutable** karar | Step statüsü değildir |
| **Requester** | Talebi açan / süreci başlatan | Actor ile aynı olmak zorunda değildir |
| **Actor** | Komutu çalıştıran user/system/worker | Requester değildir |
| **Audit Event** | Denetim amaçlı append-only kayıt | Domain event ile bire bir aynı değildir |
| **Domain Event** | Domain'de gerçekleşen durum değişikliği | Queue mesajı veya audit kaydı değildir |
| **Integration Event** | Modül sınırını geçen **versiyonlu** mesaj | İç domain event doğrudan yayınlanamaz |
| **Permission** | Actor'ün bir kaynağa eylem yetkisi | Entitlement veya feature flag değildir |

---

## 2. MVP bounded context'leri

Aşağıdaki tablo **gerçek MVP kapsamındaki** modülleri gösterir. `AI Orchestration`, `Integration/Webhook`, `Billing & Entitlements` ve `Analytics (gelişmiş)` context'leri PRD'de tanımlıdır ancak **MVP dışıdır**; MVP'de bunlar için ne tablo ne kod üretilir.

| # | Context | Sahip olduğu kavramlar (aggregate) | Sahip olduğu tablolar | Dışarı sunduğu sözleşme | MVP |
|---|---|---|---|---|---|
| 1 | **Identity** | User, external auth binding | `users` | `AuthProviderPort` ile doğrulanmış actor kimliği | ✅ |
| 2 | **Organization** | Tenant, `OrganizationMembership`, Team, Department | `tenants`, `memberships`, `teams`, `team_members` | `TenantContext`, organizasyon dizini, membership sorgusu | ✅ |
| 3 | **Authorization** | Role, Permission, Policy | `roles`, `role_permissions` | `authorize(actor, action, resource)` | ✅ |
| 4 | **Workflow Design** | `WorkflowDraft`, `WorkflowVersion`, Node, Edge, Form Schema | `workflows`, `workflow_versions`, `workflow_nodes`, `workflow_edges`, `form_schemas` | Published workflow contract (immutable, hash'li) | ✅ |
| 5 | **Workflow Runtime** | `WorkflowInstance`, Node Execution, Timer | `workflow_instances`, `node_executions`, `timers` | `WorkflowRuntimePort`: komutlar + event'ler | ✅ |
| 6 | **Work Management** | `Task`, Assignment | `tasks`, `task_assignments` | Task komutları ve inbox sorgusu | ✅ |
| 7 | **Approval** | `ApprovalRequest`, Approval Step, Approval Decision | `approval_requests`, `approval_steps`, `approval_decisions` | Karar komutları, onay durumu | ✅ |
| 8 | **Purchase Request** | `PurchaseRequest`, Form Submission | `purchase_requests`, `form_submissions` | Talep komutları ve sorguları | ✅ |
| 9 | **Document** | Document, Document Link | `documents`, `document_links` | `FileStoragePort` üzerinden güvenli upload/download | ✅ |
| 10 | **Notification** | Notification | `notifications` | Kanal-nötr gönderim isteği (MVP: yalnız in-app) | ✅ |
| 11 | **Audit** | Audit Event | `audit_events` | Append-only yazma + read-only sorgu | ✅ |
| 12 | **Analytics (temel)** | Dashboard read model | `dashboard_*` read model / view | Yetki kontrollü dashboard sorguları | ✅ (temel) |
| 13 | **Platform (shared infra)** | Outbox, Inbox, Idempotency | `outbox_events`, `processed_events`, `idempotency_keys` | Outbox yazma sözleşmesi; dispatcher | ✅ |
| — | AI Orchestration | — | — | — | ❌ MVP dışı |
| — | Integration / Webhook | — | — | — | ❌ MVP dışı |
| — | Billing & Entitlements | — | — | — | ❌ MVP dışı (sınır tasarımda korunur) |

### Import yolları (ADR-009)

| Context | Python import yolu |
|---|---|
| Identity | `flowpilot.modules.identity` |
| Organization | `flowpilot.modules.organization` |
| Authorization | `flowpilot.modules.authorization` |
| Workflow Design | `flowpilot.modules.workflow_design` |
| Workflow Runtime | `flowpilot.modules.workflow_runtime` |
| Work Management | `flowpilot.modules.work_management` |
| Approval | `flowpilot.modules.approval` |
| Purchase Request | `flowpilot.modules.purchase_request` |
| Document | `flowpilot.modules.document` |
| Notification | `flowpilot.modules.notification` |
| Audit | `flowpilot.modules.audit` |
| Analytics | `flowpilot.modules.analytics` |
| Platform | `flowpilot.modules.platform` |

Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**; erişim yalnız açık application contract, command/query veya versiyonlu integration event üzerindendir.

> **Purchase Request context'i hakkında:** PRD'de ayrı bir context olarak listelenmemiştir; ilk dikey dilim satın alma talebi olduğu için ayrı bir modül olarak konumlandırılmıştır. Bkz. [ASM-0004](../assumptions.md).

---

## 3. Sahiplik kuralı

**Bir tabloyu yalnız sahibi olan modül yazar.** Diğer modüller o veriye ancak:

- sahibinin **read model / query contract**'ı üzerinden okuyarak,
- sahibinin **command API**'si veya bir **integration event** üzerinden yazdırarak

erişir.

Örnekler:

- Approval modülü, `tasks` tablosuna **yazamaz**. Bir onay adımı için task gerekiyorsa Work Management'a komut gönderir veya bir event yayınlar.
- Notification modülü, `approval_steps` tablosunu **okuyamaz**. `approval.decided.v1` event'inin payload'ında ihtiyacı olan veriyi alır.
- Analytics, operasyonel tabloları doğrudan ağır sorgularla **yormaz**; read model üzerinden okur.
- Workflow Runtime, `workflow_versions` tablosuna **yazamaz** (immutable); yalnız okur.

---

## 4. Sistem geneli invariant'lar

Bu invariant'lar herhangi bir modül tarafından ihlal edilemez (PRD §36.1):

1. Hiçbir actor başka tenant'ın kaynağını okuyamaz veya değiştiremez.
2. Bir tenant en az bir aktif owner'a sahiptir.
3. **Published workflow version immutable'dır.**
4. Her instance **tam olarak bir** published workflow version'a bağlıdır.
5. Terminal instance yeni node başlatamaz.
6. Terminal task yeniden tamamlanamaz.
7. Bir approval step için **tek** geçerli aktif karar bulunur; tekrar komutları idempotent sonuç döndürür.
8. Karar veren actor'ün **karar anında** yetkili olduğu kanıtlanır.
9. Self-approval politikası açıkken requester kendi adımını onaylayamaz.
10. Instance cancel olduğunda açık task, approval ve timer'lar kapatılır/iptal edilir.
11. Form schema ile workflow version arasında referans bütünlüğü vardır.
12. **Audit event, business transaction başarısızsa yazılmaz.**

---

## 5. State machine'ler (MVP)

### Workflow Definition

| Mevcut | Komut | Yeni | Kural |
|---|---|---|---|
| draft | validate | draft | Hata listesi üretilir, state değişmez |
| draft | publish | published | Validation başarılı + yetki + hash |
| published | create_new_draft | draft | Published kayıt **değişmez** |
| published | deprecate | deprecated | Yeni instance varsayılanından çıkar |
| deprecated | archive | archived | Aktif instance'lar etkilenmez |

**YASAK:** `published → draft`, published kayıt üzerinde `UPDATE`, aktif instance'ın bağlı olduğu version'ı silme.

### Workflow Instance

| Mevcut | Komut / olay | Yeni |
|---|---|---|
| pending | start | running |
| running | wait_for_human | waiting |
| waiting | approval_decided / task_completed | running |
| running | all_terminal_paths_completed | completed |
| running / waiting | business_rejection_terminal | rejected |
| running / waiting | cancel | cancelled |
| running / waiting | unrecoverable_error | failed |
| failed | authorized_retry | running |

Terminal: `completed`, `rejected`, `cancelled`. (`suspended`/`resume` MVP dışı.)

### Approval Step

```text
pending -> active
active  -> approved
active  -> rejected
active  -> changes_requested
pending|active -> cancelled
```

- `approved`, `rejected`, `changes_requested`, `cancelled` **terminaldir**.
- Sıralı onayda: bir step `approved` olmadan **sonraki step aktifleşmez**.
- Karar komutu unique constraint + optimistic lock ile yarış koşuluna karşı korunur (duplicate approval → tek karar).
- `delegated`, `expired`, quorum **MVP dışıdır**.

### Task

```text
open -> in_progress -> completed
open|in_progress -> cancelled
```

`overdue` ayrı state değil, **türetilmiş alandır** (`is_overdue`). Aynı kavram iki yerde tutulmaz.

---

## 6. MVP node seti

Yalnız: `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`.

**Kapsam dışı (implemente edilmez):** parallel split/join, quorum approval, sub-workflow, webhook node, script node, AI node, DMN, görsel workflow canvas.

Bilinmeyen node tipi **yayınlanamaz**. Yeni node tipi eklemek owner kararıdır ve ADR gerektirir.
