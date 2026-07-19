# modules/purchase_request — Purchase Request

**Sahip olduğu kavramlar:** `PurchaseRequest` (+ Money, Title/Description value object'leri, `PurchaseRequestCreated` event).
**Sahip olduğu tablolar:** `purchase_request_requests` (migration `0004`).

## Durum

✅ **Dikey dilim + onay akışı yazıldı** (Create → workflow → sıralı onay → PR status →
timeline). Kalan: frontend ekranları (sonraki aşama).

> Not: Bu context PRD §35.1'in bounded context tablosunda ayrıca listelenmemiştir; ilk dikey dilim satın alma talebi olduğu için ayrı modül olarak konumlandırılmıştır ([ASM-0004](../../../../../../docs/assumptions.md)).

## Katmanlar

```text
domain/          # identifiers, errors, money, value_objects, purchase_request
                 #   (aggregate + create/attach/approve/reject transitions + event)
application/     # dto, errors, workflow (default definition loader), ports,
                 #   create_handler (atomik use-case), get_handler, approval_link
                 #   (onay akışı için yazma sözleşmesi); resources/ (versioned JSON)
infrastructure/  # persistence: tables, repository (get_by_workflow_instance), read_query
                 #   (get + list_for_requester)
```

## Domain modeli ve para

- **`PurchaseRequest`** alanları: id, tenant_id, requested_by, title, description (opsiyonel), money (amount_minor + currency), status, workflow_instance_id, created_at, updated_at, version (optimistic).
- **Para minor unit + currency** (FF-09): `amount_minor` BIGINT, float YOK, `> 0`. **MVP'de yalnız TRY.** 10.000 TL = 1.000.000 minor unit; 50.000 TL = 5.000.000.
- **Başlık** 1-200 karakter, boş/whitespace olamaz. **Açıklama** opsiyonel, ≤ 2000 karakter. Sunucu tarafı doğrulama zorunlu.
- **Onay eşikleri koda HARD-CODE EDİLMEZ** ([ASM-0001](../../../../../../docs/assumptions.md)); versioned workflow definition'ın Condition node'undadır.

## Default workflow provisioning

Visual designer / public publish endpoint YOKKEN tenant başına varsayılan workflow
(`purchase_request_approval` v1) **idempotent + concurrent-safe** provision edilir
(`WorkflowRuntimeProvisioningPort.ensure_published_definition`). Mevcut published version
yeniden kullanılır; aynı key/version farklı hash ile **sessizce overwrite edilmez**. Definition
`application/resources/purchase_request_approval_v1.json` package resource'undadır. Bu bir
public HTTP endpoint DEĞİLDİR.

**Eşik bantları (definition'da):** <10.000 TL → team_manager · 10.000-50.000 TL →
team_manager + finance · >50.000 TL → team_manager + finance + general_manager.

## Cross-module ATOMİK transaction

`CreatePurchaseRequest`, Purchase Request kaydını **ve** workflow instance başlangıcını
(instance + ilk approval task + event + outbox) **ve denetim kayıtlarını** (`purchase_request.created`
→ `workflow.started` → `approval.task_assigned`) **AYNI transaction'da** commit eder. Bu,
composition root'ta ([api/wiring.py](../../api/wiring.py)) kurulan **compose UnitOfWork**
ile sağlanır: modüllerin adapter'ları (runtime + purchase_requests + audit) TEK SQLAlchemy
session'ı üzerinde birleşir. Runtime tarafı, kod kopyalanmadan `WorkflowRuntimeTransactionPort`
(`start_instance_tx`/`submit_form_tx` — commit etmez, sağlanan uow üzerinde çalışır) ile;
audit tarafı `AuditWriterPort` ile katılır. Cross-module infrastructure importu YOKTUR; iki
bağımsız commit YOKTUR; port'ların provider-neutral sınırı korunur. Bkz. [ASM-0015](../../../../../../docs/assumptions.md).

### Onay akışının PR'a yansıması (approval_link)

Approval modülü, `purchase_request.domain`'i import ETMEDEN — cross-context domain importu
YASAK (dependency-rules §2) — bir kararın PR'a yansımasını `application/approval_link.py`
üzerinden uygular: `apply_workflow_outcome` (workflow `completed`→approve, `rejected`→reject;
IN_APPROVAL→APPROVED/REJECTED geçişi PR domain'inde kalır) ve `resolve_purchase_request_id`.

## Authorization

Yalnız tenant içinde **aktif membership** sahibi kullanıcı talep oluşturabilir (`MembershipQuery`
organization application contract'ı; organization infrastructure'a doğrudan erişilmez). Kimlik
`CurrentActor`'dan gelir; request body'den user/tenant/workflow/approver override alınmaz.
Path'teki `organization_id` tek başına yetki sağlamaz — membership ile doğrulanır.

## Endpoint'ler

- **`POST /v1/organizations/{organization_id}/purchase-requests`** → 201; talep oluşturur, workflow başlatır, ilk approval task'ını üretir.
- **`GET /v1/organizations/{organization_id}/purchase-requests`** → actor'ın YALNIZ kendi talepleri, en yeni önce (server-side max page size; unbounded list YOK).
- **`GET /v1/organizations/{organization_id}/purchase-requests/{id}`** → talep + workflow durumu + current approval role.
- **`GET /v1/organizations/{organization_id}/purchase-requests/{id}/timeline`** → kronolojik, append-only audit timeline (tenant-scoped; hassas değer içermez).

Onay kararı + kişisel inbox endpoint'leri `tasks` router'ındadır (approval modülü); bkz.
[modules/approval](../approval/README.md). Public runtime API'si yoktur; runtime application
servisi yalnız içeriden çağrılır.

## RLS

`purchase_request_requests` tenant-scoped: RLS ENABLE + FORCE + tenant policy. Missing context →
DEFAULT DENY. Cross-tenant IDOR engellenir. `flowpilot_app` NOBYPASSRLS. `workflow_instance_id`,
runtime instance'ına MANTIKSAL referanstır (cross-module FK YOK — [ASM-0012](../../../../../../docs/assumptions.md) gerekçesi).
