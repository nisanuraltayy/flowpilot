# modules/workflow-runtime — Workflow Runtime

**Sahip olduğu kavramlar:** `WorkflowInstance`, NodeExecution, Timer.
**Sahip olduğu tablolar:** `workflow_instances`, `node_executions`, `timers`.

## ⛔ LOCK-003 — Spike şartına bağlı

**Bu modüle bağlı kalıcı üretim kodu, workflow runtime spike'ının 12/12 exit criterion'u kanıtlanmadan YAZILAMAZ** (ADR-004). Bkz. [spike planı](../../docs/architecture/workflow-runtime-spike-plan.md).

Spike başarısız olursa Temporal yeniden değerlendirilir. `WorkflowRuntimePort` bu geçişi domain kodunu yeniden yazmadan mümkün kılmak için vardır.

## Sorumluluk

Sürecin **çalışması**. Instance yaşam döngüsü, node yürütme, condition evaluation, persisted timer.

## Sınırlar

- **`WorkflowRuntimePort` burada tanımlanır**; uygulama katmanı somut runtime'a doğrudan bağımlı olamaz.
- Her instance **tam olarak bir** published version'a bağlıdır. Runtime, node tanımını instance'ın bağlı olduğu version'dan okur — **asla "son yayınlanan"dan değil** (SPK-02).
- **Terminal instance yeni node başlatamaz** — guard API, event handler ve timer yollarının **hepsinde** uygulanır (SPK-09).
- State transition + outbox + audit **aynı transaction**'da yazılır (SPK-11).
- Condition evaluator: güvenli DSL. **`eval`/`exec` YASAK** (FF-08). Deterministik ve açıklanabilir olmalı.
- Timer'lar **veritabanındadır**; in-memory timer YASAK.
- `workflow_versions` tablosuna **yazamaz** (immutable) — yalnız okur.

## Durum

Boş.
