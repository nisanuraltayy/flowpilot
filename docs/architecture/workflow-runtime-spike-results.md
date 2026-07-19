# Workflow Runtime Spike — Sonuç Raporu

- **Durum:** ✅ **12/12 exit criterion PASS**
- **Tarih:** 2026-07-19
- **İlgili:** [ADR-004](../adr/ADR-004-workflow-runtime-spike.md), [spike planı](workflow-runtime-spike-plan.md), Epic E08, LOCK-003
- **Spike kodu:** [spikes/workflow-runtime/](../../spikes/workflow-runtime/) — **geçici, production kodu değildir**

> Bu rapor bir karar dokümanıdır. Spike kodu üretim kodu **değildir**; production runtime (E09) `WorkflowRuntimePort` arkasında sıfırdan yazılacaktır. Spike'ın çıktısı **karar ve kanıttır**.

---

## 1. Test edilen yaklaşım

Custom, hafif, **PostgreSQL-backed** workflow runtime prototipi. Referans akış:
`Start → Form → Condition (tutar) → Sequential Approval → Notification → End`.

Tasarımın temel kararları:

- **Tek veritabanı, tek transaction sınırı.** State transition + outbox event + audit event **aynı PostgreSQL transaction'ında** yazılır. Engine fonksiyonları COMMIT etmez; transaction sınırı komut katmanına aittir (dual write yok).
- **Immutability üç bağımsız katmanla:** (1) kod yolunda published version'a `UPDATE` yok, (2) role `UPDATE` grant'ı verilmez, (3) `BEFORE UPDATE/DELETE` trigger'ı tablo sahibini bile engeller. Aynı trigger `audit_events` ve `approval_decisions` için de append-only'i zorlar.
- **Güvenli condition evaluator:** `eval`/`exec` yok; koşullar whitelist'li operatörlerle saf veri olarak yorumlanır. Tutarlar **minor unit (int) + ISO-4217 currency**; float yok. Eşikler workflow definition'dan gelir, koda hard-code edilmez.
- **Outbox dispatcher:** `FOR UPDATE SKIP LOCKED` + lease (`claim_expires_at`). İşleme = idempotent inbox kaydı (`processed_events` PK) + side effect + `processed` işareti **aynı transaction'da**. At-least-once + idempotent consumer; "exactly once" iddiası yok.
- **Persisted timer:** `timers` tablosunda yaşar; in-memory scheduler yok. Fake clock enjekte edilebilir.
- **Optimistic concurrency:** `instances.version` ve `approval_steps.version` üzerinde compare-and-swap; duplicate approval için ek olarak `approval_decisions.step_id UNIQUE`.
- **Tenant izolasyonu:** her tablo `tenant_id` + RLS **ENABLE + FORCE**; roller (`spike_app`, `spike_worker`) **NOSUPERUSER + NOBYPASSRLS**. Tenant scope transaction-local `set_config(..., true)` ile taşınır.

**Teknoloji:** Python 3.13, SQLAlchemy 2.0.51 (Core, raw SQL), psycopg 3.3.4, PostgreSQL 17.10 (Testcontainers). Yeni runtime dependency eklenmedi.

---

## 2–4. ADR-004 exit criteria: kriter-kanıt tablosu

Aşağıdaki 12 kriterin **tamamı** gerçek PostgreSQL üzerinde otomatik testle kanıtlanmıştır. Kısmi başarı yoktur.

| # | Kriter | Sonuç | Kanıt (test) |
|---|---|---|---|
| **SPK-01** | Published version immutable | ✅ **PASS** | `test_spk01_immutability::test_published_version_is_immutable` (app UPDATE reddi + owner trigger reddi + v1 hash bit-sabit); `unit/test_static_safety::test_no_update_path_to_published_versions` |
| **SPK-02** | Instance başladığı version'a sabit | ✅ **PASS** | `test_spk02_version_pinning::test_pending_instance_completes_with_v1_semantics` (v2 yayınlanırken bekleyen instance v1 ile tamamlanır); `test_state_reload_is_deterministic` |
| **SPK-03** | Condition doğru + güvenli branch | ✅ **PASS** | `unit/test_conditions` (sınır değer tablosu 9.999,99/10.000,00/10.000,01 TL + zararlı payload çalıştırılmadan reddedilir + determinizm); `test_spk03_condition_runtime` (runtime branch → doğru zincir) |
| **SPK-04** | Sıralı onay sırası korunur, asılı kalmaz | ✅ **PASS** | `test_spk04_sequential_order::test_sequence_cannot_be_skipped_and_does_not_hang` (erken karar reddi + karar kaydı yok + audit; sonra 1. onay 2. adımı aktive eder) |
| **SPK-05** | Duplicate approval → tek karar | ✅ **PASS** | `test_spk05_duplicate_approval` (eşzamanlı çift tıklama, sıralı retry, iki farklı onaycı yarışı → tek karar, tek geçiş, tek event) |
| **SPK-06** | Duplicate event → tek side effect | ✅ **PASS** | `test_spk06_idempotent_inbox::test_redelivered_event_produces_no_second_side_effect` + `test_two_workers_cannot_claim_same_event` (SKIP LOCKED) |
| **SPK-07** | Worker crash → süreç kayıpsız + duplicate'siz | ✅ **PASS** | `test_spk07_crash_recovery` — gerçek subprocess **SIGKILL** (TerminateProcess): (a) dispatch edilmemiş event restart'ta tamamlanır, (b) claim ortasında crash → lease dolunca yeniden alınır, tek side effect |
| **SPK-08** | Persisted timer restart'tan sağ çıkar, tam bir kez ateşler | ✅ **PASS** | `test_spk08_timers::test_timer_survives_restart_and_fires_exactly_once` (fake clock + subprocess restart); `test_two_workers_cannot_claim_same_timer` |
| **SPK-09** | Terminal instance hiçbir yoldan ilerletilemez | ✅ **PASS** | `test_spk09_terminal_guard` — (a) gecikmeli komut, (b) cancel açık step/timer kapatır + karar reddi, (c) geciken timer diriltemez, + invalid transition kontrollü reddedilir |
| **SPK-10** | Cross-tenant erişim iki katmanla engelli | ✅ **PASS** | `test_spk10_tenant_isolation` — context'siz 0 satır, filtresiz sorgu yalnız RLS ile izole, gerçek UUID ile IDOR sızdırmaz, RLS WITH CHECK cross-tenant yazımı reddeder, roller BYPASSRLS'siz |
| **SPK-11** | State + outbox + audit atomik | ✅ **PASS** | `test_spk11_atomicity::test_fault_before_commit_rolls_back_everything` (fault injection → dört tablo da değişmez); `test_side_effect_failure_keeps_state_and_produces_bounded_retry_incident` |
| **SPK-12** | Concurrency conflict kontrollü | ✅ **PASS** | `test_spk12_optimistic_concurrency` (bayat step/instance version → 409 benzeri; eşzamanlı submit → tek kazanan + kontrollü conflict, deadlock yok; tüm mutable aggregate'lerde version alanı) |

**Toplam: 12 PASS / 0 FAIL / 0 PARTIAL.**

Test paketi: **72 test** (unit + integration + concurrency + crash-recovery + benchmark), tümü yeşil.

---

## 5. Concurrency sonucu

- **Duplicate approval (SPK-05):** `ThreadPoolExecutor` ile eşzamanlı iki karar komutu → `approval_decisions` tablosunda tam **1** satır, outbox'ta tam **1** `approval.decided.v1`, workflow bir kez ilerledi. Aynı actor+idempotency key → idempotent replay; farklı actor → kontrollü `DuplicateDecision`/`StaleVersion`. Koruma **DB düzeyinde** (`UNIQUE(step_id)` + version CAS), uygulama düzeyi "önce oku sonra yaz" değil.
- **Eşzamanlı form submit (SPK-12):** İki thread aynı version'ı okuyup ilerletmeye çalışır → tam **bir** kazanan, diğeri kontrollü conflict (`StaleVersion` veya `InvalidTransition`). Optimistic guard step insert'lerinden **önce** çalıştığı için ham `IntegrityError` sızmaz. Deadlock gözlenmedi.
- **Claim yarışı (SPK-06/SPK-08):** `FOR UPDATE SKIP LOCKED` ile iki worker aynı outbox event'ini/timer'ını asla birlikte claim etmedi.

## 6. Crash recovery sonucu (SPK-07)

Gerçek `subprocess` worker, bir event'in claim'i commit edildikten **sonra** işleme başlamadan **zorla öldürüldü** (Windows `Process.kill()` = `TerminateProcess`, SIGKILL eşdeğeri; graceful shutdown değil). Sonuç:

- Crash sonrası event `pending` durumda kaldı (kayıp yok), lease yazılıydı, side effect üretilmemişti.
- Lease süresi dolunca yeniden başlatılan worker event'i tekrar aldı ve süreci **tek** bildirimle tamamladı.
- İkinci restart de duplicate üretmedi (inbox koruması). Hiçbir instance kalıcı `waiting`/`running` durumunda asılı kalmadı.

## 7. Idempotency sonucu (SPK-06)

Aynı `event_id`'nin yeniden teslimi (`processed_events` inbox kaydı sayesinde) **hiçbir** yeni side effect üretmedi: bildirim, audit, node execution ve state sayıları sabit kaldı. İkinci işleme `duplicate` olarak işaretlendi, event yeniden `processed` yapıldı.

## 8. Tenant isolation sonucu (SPK-10)

Beş cross-tenant erişim denemesi (oku, iptal et, karar ver, timeline oku, notification oku) **tamamı** reddedildi; kaynak varlığı sızdırılmadı (gerçek UUID ile rastgele UUID aynı `NotFound` davranışı). Uygulama filtresi bilinçli kaldırıldığında **RLS tek başına** sorguyu boşa düşürdü (ikinci savunma katmanı kanıtı). `spike_app`/`spike_worker` rolleri `rolbypassrls=false`, `rolsuper=false`. Worker business tablolarında tenant-scoped; yalnız kuyruk tablolarını (outbox/timer/inbox) tenant-üstü yönetir.

## 9. Transaction rollback sonucu (SPK-11)

Commit'ten hemen önce fault injection → karar, state değişikliği, outbox event'i ve audit kaydının **hiçbiri** yazılmadı (kısmi durum yok). Hata kaldırılınca üçü birlikte yazıldı. Side effect başarısızlığı (bildirim kanalı çöküşü simülasyonu) state'i **geri almadı**; bounded retry (MAX_ATTEMPTS=5) tükenince `failed` + audit incident üretti — başarısızlık kullanıcıdan gizlenmedi. Sonsuz retry yok.

## 10. Benchmark sonuçları

> ⚠️ Bu bir performans ürünü değildir; kaba büyüklük ölçümüdür. **Production kapasite iddiası içermez.**
> **Ortam:** tek makine, Windows 11 + Docker Desktop 29.2.1 (WSL2), Testcontainers PostgreSQL 17.10, Python 3.13, monotonic clock. Container soğuk başlatma dahil değil.

| Ölçüm | Sonuç |
|---|---|
| Tek instance başlatma + form submit | ~50 ms |
| Tek approval transition (komut sınırı, kendi transaction'ı) | ~12 ms |
| 100 küçük instance uçtan uca (start → onay) | ~4,0 s (instance başına p50 ~25 ms, p95 ~70 ms) |
| Worker kuyruk boşaltma (403 event) | ~2,0 s |
| Eşzamanlı claim (2 worker, 80 event, SKIP LOCKED) | ~17 ms, çift-claim yok |

Rakamlar tek node PostgreSQL için makul; darboğaz beklendiği gibi round-trip başına transaction maliyetidir. Ölçek ihtiyacı doğduğunda batch dispatch ve connection pooling ile iyileştirilebilir (production tasarım notu).

---

## 11. Tespit edilen riskler

1. **Timer yoğunluğu:** Polling worker + `SKIP LOCKED` yaklaşımı MVP hacmi için yeterli; tenant başına on binlerce eşzamanlı timer'da polling aralığı ve index stratejisi yeniden değerlendirilmelidir (ADR-004 yeniden değerlendirme tetikleyicisiyle uyumlu).
2. **Lease süresi ayarı:** Çok kısa lease, yavaş bir handler ortasında event'in yeniden claim'ine yol açabilir. İdempotent consumer bunu güvenli kılar (duplicate side effect yok) ama gereksiz iş üretir. Production'da lease, en yavaş handler p99'una göre ayarlanmalıdır.
3. **`otherwise` dalı ve currency:** Condition evaluator farklı para birimini reddediyor; MVP tek-currency (TRY) varsayımıyla uyumlu ([ASM-0002](../assumptions.md)). Çoklu currency gelirse eşik karşılaştırma semantiği yeniden ele alınmalı.
4. **Spike ölçek dışı bırakılanlar:** Retry backoff sabitleri, DLQ görünürlüğü, metrik/trace ihracı spike'ta minimaldir; production'da observability tam bağlanmalıdır.

## 12. Production implementation için önerilen minimal tasarım

`WorkflowRuntimePort` arkasında, aşağıdaki spike-kanıtlı kararlarla:

- **Engine fonksiyonları COMMIT etmez.** Transaction sınırı application command handler'ında; state + outbox + audit tek `UnitOfWork` içinde (mevcut `flowpilot` UoW pattern'iyle uyumlu).
- **Immutability:** published tablolar için grant kısıtı + DB trigger; kod yolunda UPDATE olmadığını doğrulayan fitness check (FF-11 zaten mevcut).
- **Dispatcher:** `outbox_events` + `processed_events` (inbox) + lease'li `SKIP LOCKED`; bounded retry + `failed` durumu + incident audit.
- **Timer:** `timers` tablosu + aynı dispatcher döngüsünde vade kontrolü; terminal instance guard'ı dispatcher'da ikinci savunma olarak.
- **Guard'lar merkezi:** terminal instance, sıra, yetki, self-approval kontrolleri policy/transition katmanında — event handler dahil **her** giriş yolunda uygulanır (arka kapı yok).
- **Optimistic concurrency:** her mutable aggregate'te `version`; approval için ek `UNIQUE(step_id)` terminal decision.
- **RLS:** production'da worker rolü de `NOBYPASSRLS`; worker tenant context'ini her event için event payload'ındaki `tenant_id`'den kurar.

Spike şeması **production migration değildir**; E09'da Alembic ile bounded context tabloları (`workflow_instances`, `node_executions`, `timers`, `approval_*`, `outbox_events`, `processed_events`) domain-boundaries.md sahipliğine göre üretilecektir.

## 13. Temporal fallback kararı

**Gerekli değildir.** ADR-004'ün yedeği olan Temporal, ancak bir veya daha fazla exit criterion kanıtlanamazsa devreye girecekti. 12/12 kriter PostgreSQL-backed custom runtime ile kanıtlandığından, ADR-004'ün ana kararı (custom runtime) geçerlidir. En kritik ayrım — **state + outbox + audit'in aynı transaction'da atomikliği** (SPK-11) — custom runtime'da doğal olarak elde edildi; Temporal bunu ayrı durable store gerektirerek zorlaştırırdı.

## 14. LOCK-003 kararı

**LOCK-003 kapatılabilir.** ADR-004'ün koşulu ("12 exit criterion'un tamamı kanıtlanmadan runtime'a bağlı kalıcı üretim kodu yazılamaz") **karşılanmıştır**. Öneri:

1. ADR-004 durumu `Accepted (conditional)` → **`Accepted`** olarak güncellensin; koşul referansı bu rapora bağlansın.
2. LOCK-003 `KOŞULLU` → **KAPALI** olarak işaretlensin (CLAUDE.md §4, AGENTS.md §3, docs/adr/README.md).
3. Sıradaki story: **Epic E09 — Workflow Runtime Core** (`WorkflowRuntimePort` arkasında production implementation). Backlog'daki `blocked_by: E08` engeli kalkar.

> **Not:** Bu ADR/lock güncellemeleri ve E09'a geçiş **owner onayına tabidir**. Bu rapor kararı ve kanıtı sunar; ADR/lock dosyaları henüz değiştirilmemiştir.

---

## Ek: kalite kapıları (bu spike)

| Kapı | Sonuç |
|---|---|
| Spike unit + integration + concurrency + crash-recovery testleri | ✅ 72/72 |
| Ruff check | ✅ |
| Ruff format --check | ✅ |
| mypy --strict (src) | ✅ 10 dosya, 0 sorun |
| Backend regresyon (`pytest apps/backend/tests`) | ✅ 93/93 |
| Backend ruff / format / mypy / import-linter / AST boundary | ✅ tümü |
| Production kaynak / migration / API / worker / frontend / `.env` değişimi | ✅ **yok** (yalnız `spikes/` + bu rapor) |
