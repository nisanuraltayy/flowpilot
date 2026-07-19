# modules/approval — Approval

**Sahip olduğu kavramlar:** `ApprovalRoleAssignment`, `ApprovalDecision`, `ApprovalComment`.
**Sahip olduğu tablolar:** `approval_role_assignments`, `approval_decisions`.

> Sıralı adım (step) state'i ve aktivasyonu **workflow_runtime**'a aittir
> (`workflow_runtime_tasks`). Approval modülü, atanmış onaycı tarafından verilen
> **kararı** kaydeder ve bu kararı runtime + purchase_request + audit ile TEK
> transaction'da birleştirir. İkinci bir approval-step source-of-truth **yoktur**.

## Sorumluluk

Onay motorunun karar katmanı — ürünün çekirdek değeri. MVP node seti: Sequential
Approval (1–3 adım), **approve / reject** (changes_requested MVP dışı).

### Rol atamaları (owner-approved MVP)

- Tenant başına **üç** approval role key: `team_manager`, `finance`, `general_manager`.
- Her role key için tenant'ta **tek aktif assignee** (partial unique index:
  `(tenant_id, role_key) WHERE status='active'`). Aynı kullanıcı birden fazla rol taşıyabilir.
- Organizasyonun rolleri henüz oluşmamışsa, ilk onay akışından önce **üç rol de aktif
  owner'a idempotent** atanır (`EnsureDefaultApprovalRoleAssignments`). Bu **public bir
  role-management endpoint'i DEĞİLDİR**; tekrar çalıştırıldığında duplicate üretmez,
  mevcut açık atamaları OVERWRITE ETMEZ, aktif owner yoksa kontrollü configuration error
  (`ActiveOwnerNotFoundError`) üretir. Bkz. [[ASM-0016]].
- Task oluşturulduğunda role'e atanmış kullanıcı **task'a SABİTLENİR** (pin). Rol ataması
  sonradan değişse bile mevcut açık task'ın assignee'si değişmez; yeni task'lar güncel
  atamayı kullanır (owner #5). Pinning `workflow_runtime` task'ında tutulur
  (`assigned_user_id`).

## Sınırlar (güvenlik-kritik)

- **Bir approval step için tek geçerli terminal karar bulunur.** Duplicate koruması
  **veritabanı düzeyindedir**: `approval_decisions.task_id` unique + `(tenant_id,
  idempotency_key)` unique + runtime optimistic version CAS. Uygulama seviyesinde "önce
  oku, yoksa yaz" tek başına YETERSİZDİR (SPK-05). Eşzamanlı iki karar → **tek kazanan**.
- **Yetki assignee iledir (owner #6):** yalnız task'ın `assigned_user_id`'sine eşit
  authenticated kullanıcı karar verebilir; başka kullanıcı varlık sızdırmayan reddedilir.
- **Self-approval MVP'de SERBEST** (owner #7): requester kendi adımını onaylayabilir —
  tek kullanıcının tüm akışı uçtan uca test etmesini sağlar. Bu **geçici, owner onaylı bir
  ürün kararıdır**, güvenlik açığı değildir; separation-of-duties pilot'a ertelendi. Gizli
  feature flag veya hard-code kullanıcı istisnası **DEĞİL** — auth yalnızca assignee'ye
  dayanır. Bkz. [[ASM-0016]].
- **Sıra atlanamaz:** sonraki step, öncekisi tamamlanmadan aktifleşmez (runtime; SPK-04).
- **Sıra asılı kalamaz:** karar + runtime task transition + sonraki task + PR status +
  `ApprovalDecision` + runtime event/outbox + audit entry **aynı transaction**'dadır
  (`DecideApprovalTaskHandler`). Commit başarısızsa hiçbir kısmi state kalmaz.
- `ApprovalDecision` **immutable**'dır (append-only; UPDATE/DELETE grant yok + trigger).
- İdempotency: aynı `Idempotency-Key` replay → aynı sonuç (duplicate=True); farklı
  payload/çakışan karar → `409`.

## Katman sınırları (dependency-rules §2)

- Approval, `workflow_runtime` / `purchase_request` / `audit` modüllerinin
  **infrastructure veya domain** katmanını IMPORT ETMEZ. Cross-module etkileşim yalnız
  **application contract'ları** üzerinden: runtime `WorkflowRuntimeTransactionPort`,
  audit `AuditWriterPort` + `AuditRecord`, PR `apply_workflow_outcome` /
  `resolve_purchase_request_id` application fonksiyonları.
- Compose UoW (runtime + PR + approval_decisions + audit, tek session) yalnız
  **composition root**'ta (`api/wiring.py`) kurulur.

## Durum

**Uygulanmış (backend).** Role assignment provisioning, karar use-case'i (atomik),
kişisel inbox ve audit timeline entegre. MVP dışı: parallel approval, quorum,
delegation, eskalasyon, changes_requested.
