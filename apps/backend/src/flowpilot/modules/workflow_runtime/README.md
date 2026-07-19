# modules/workflow_runtime — Workflow Runtime Core (E09)

**Sahip olduğu kavramlar:** `WorkflowDefinitionVersion`, `WorkflowInstance`, `WorkflowTask`, `WorkflowEvent`, Timer, transactional outbox, idempotent inbox.
**Sahip olduğu tablolar (hepsi `workflow_runtime_` önekli):** `workflow_runtime_definitions`, `workflow_runtime_definition_versions`, `workflow_runtime_instances`, `workflow_runtime_tasks`, `workflow_runtime_events`, `workflow_runtime_outbox`, `workflow_runtime_inbox`, `workflow_runtime_timers` (migration `0003`).

## Durum

✅ **Production runtime core yazıldı** (Epic E09). ADR-004 spike'ının 12/12 kanıtladığı
yaklaşım, mevcut mimari (module boundaries, SQLAlchemy 2.0, Alembic, RLS, UnitOfWork,
worker) üzerinde production kalitesinde uygulandı. Spike kodu
([spikes/workflow-runtime/](../../../../../../spikes/workflow-runtime/)) yalnız
tarihsel/teknik kanıttır; production bu dizini **import etmez**.

- **LOCK-003 KAPANDI** (2026-07-19, ADR-004 Accepted). Runtime'a bağlı üretim kodu artık serbesttir.
- **Purchase Request + Approval akışlarına bağlıdır.** Runtime `WorkflowRuntimeTransactionPort`
  (tx-metodları) üzerinden compose transaction'a katılır; `WorkflowRuntimeProvisioningPort`
  ile varsayılan definition idempotent provision edilir. Public HTTP runtime API'si yoktur —
  yalnız purchase_request/approval application katmanları içeriden çağırır.

### Task assignee pinning (owner #5) + karar akışı

- `workflow_runtime_tasks.assigned_user_id` (migration `0005`): task **oluşturulduğu anda**
  role'e atanmış kullanıcı SABİTLENİR. `SubmitFormCommand.role_assignees` (role_key → user_id)
  ile geçirilir. Rol ataması sonradan değişse bile mevcut açık task'ın assignee'si DEĞİŞMEZ.
- Yetki `assigned_user_id` iledir (owner #6): assignee sabitse yalnız o kullanıcı karar
  verebilir (`UnauthorizedApproverError`); assignee None ise (legacy/test) rol eşleşmesine düşülür.
- `decide_task_tx(...)` COMMIT ETMEZ; sağlanan compose UoW üzerinde çalışır — approval
  kararının PR status + `ApprovalDecision` + audit ile TEK transaction'da birleşmesini sağlar.
- **Terminal-task idempotency:** nihai adımın (instance'ı tamamlayan/reddeden) kararı **aynı
  actor + aynı key** ile replay edilirse `TerminalInstanceError` değil güvenli idempotent
  duplicate (duplicate=True) döner; farklı actor/key ise terminal instance → `TerminalInstanceError`
  (SPK-09 korunur), canlı instance'ta terminal task → `DuplicateDecisionError`.

## Katmanlar

```text
domain/          # saf: identifiers, enums, errors, conditions, definition (+validation/hash),
                 #      instance, task, event — framework/ORM/SDK importu YOK
application/      # dto (typed command/result), port (WorkflowRuntimePort + repo/UoW port'ları),
                 #      service (WorkflowRuntimeService — use-case orkestrasyonu)
infrastructure/  # persistence: tables (module-owned metadata), repositories (aggregate-specific),
                 #      unit_of_work (transaction + RLS context)
```

## WorkflowRuntimePort

Uygulamanın geri kalanının (API, worker, purchase_request) gördüğü provider-neutral
yüzey ([application/port.py](application/port.py)). SQLAlchemy model/session **döndürmez**;
girdi/çıktı typed DTO'dur. Yetenekler: publish_definition, start_instance, submit_form,
decide_task, cancel_instance, schedule_timer, load_instance, get_timeline,
run_dispatch_pass. Somut implementasyon `WorkflowRuntimeService`; wiring yalnız
composition root'ta (`worker/wiring.py`, ileride `api/deps.py`).

## Kanıtlanan invariant'lar (spike → production)

- **Immutable version** (SPK-01): published version'a UPDATE yolu yok + grant yok + `BEFORE UPDATE/DELETE` trigger. `content_hash` canonical JSON'dan üretilir.
- **Version pinning** (SPK-02): her instance `definition_version_id` + `definition_hash`'e sabittir; runtime node'u instance'ın bağlı olduğu version'dan okur — asla "son yayınlanan"dan değil.
- **Güvenli condition** (SPK-03): `eval`/`exec` YOK; whitelist operatör; minor unit + currency; deterministik + açıklanabilir.
- **Sıralı onay** (SPK-04): bir adım approved olmadan sonraki aktifleşmez; sıra asılı kalmaz.
- **Duplicate approval** (SPK-05): optimistic version CAS → tek kazanan; idempotent replay.
- **Idempotent inbox** (SPK-06): `workflow_runtime_inbox` (event_id, consumer) PK → duplicate event tek side effect.
- **Crash recovery** (SPK-07): outbox lease (`claim_expires_at`) → crash eden worker'ın işi lease dolunca yeniden alınır.
- **Persisted timer** (SPK-08): `workflow_runtime_timers` DB'de; in-memory timer YOK; tam bir kez ateşler.
- **Terminal guard** (SPK-09): terminal instance API/event/timer hiçbir yoldan ilerletilemez.
- **Cross-tenant izolasyon** (SPK-10): her tablo `tenant_id` + RLS ENABLE+FORCE + tenant policy; flowpilot_app NOBYPASSRLS.
- **Atomiklik** (SPK-11): state + task + event + outbox AYNI transaction (UnitOfWork sınırı); dual write yok.
- **Optimistic concurrency** (SPK-12): mutable aggregate'lerde `version` CAS → conflict kontrollü hata (ConcurrencyConflictError).

## Transaction, outbox/inbox, timer/lease modeli

- **Transaction sınırı UnitOfWork'tedir**; engine/repository içinden rastgele commit YOK.
- **Outbox** (ADR-007): state değişikliğiyle aynı transaction'da yazılır; dispatcher `FOR UPDATE SKIP LOCKED` + lease ile claim eder.
- **Inbox**: side effect + inbox kaydı + outbox 'processed' işareti aynı transaction'da.
- **Bounded retry**: `MAX_ATTEMPTS=5` + exponential backoff; limitte `failed` (sonsuz retry YOK). "Exactly once" iddiası YOK (at-least-once + idempotent consumer).
- **Dispatcher tenant-scoped çalışır**: her tur açık bir `tenant_id` context'i altında; kuyruk tabloları da RLS'e tabidir (queue-wide bypass YOK). Çoklu-tenant zamanlama sonraki bir story'ye bırakılmıştır (bkz. [ASM-0014](../../../../../../docs/assumptions.md)).

## Modül sınırı notu (ASM-0013)

Bu runtime core, definition-version / task / event / outbox / inbox sorumluluklarını
`workflow_runtime` altında **geçici olarak konsolide eder**. domain-boundaries.md
bunları workflow_design / work_management / approval / platform'a dağıtır; o modüller
oluştuğunda sınır uzlaştırması yapılacaktır. Çakışmayı önlemek için tüm tablolar
`workflow_runtime_` öneklidir. Bkz. [ASM-0013](../../../../../../docs/assumptions.md).
