# ADR-004 — Workflow Runtime: `WorkflowRuntimePort` Arkasında Custom PostgreSQL-Backed Runtime

- **Durum:** **Accepted** — spike 12/12 exit criterion geçti (2026-07-19)
- **Tarih:** 2026-07-14 (koşullu kabul) · 2026-07-19 (kesin kabul)
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-003 (**KAPALI** — 2026-07-19)
- **İlgili PRD bölümleri:** §9.7, §12, §26, §36.2, §36.3, §37, §38.6

> **Spike sonucu (2026-07-19):** `WorkflowRuntimePort` arkasındaki custom
> PostgreSQL-backed runtime yaklaşımı, ADR-004'ün **12 exit criterion'unun
> tamamıyla** (SPK-01…SPK-12) gerçek PostgreSQL üzerinde kanıtlandı. Spike
> commit'i: **`6cbbb7f`** (`spike: validate PostgreSQL workflow runtime`).
> Kanıt paketi ve benchmark: [workflow-runtime-spike-results.md](../architecture/workflow-runtime-spike-results.md).
> Bu ADR `Accepted (conditional)` → **`Accepted`** oldu ve **LOCK-003 kapandı**.
> **Not:** Production runtime implementasyonu (Epic E09) **henüz yazılmamıştır**;
> spike kodu ([spikes/workflow-runtime/](../../spikes/workflow-runtime/)) üretim
> kodu değildir. Bu kabul, E09'un `WorkflowRuntimePort` arkasında yazılabilmesinin
> önündeki kilidi kaldırır.

## Bağlam

Workflow runtime FlowPilot'ın kalbidir. PRD dört seçenek bırakmıştı: custom hafif motor, Temporal, Camunda 8, hibrit.

Gerçek MVP node seti **çok dardır**: `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`. Parallel split/join, quorum, sub-workflow, script, DMN ve AI node **kapsam dışıdır**. Bu, "tam BPM motoru" gereksinimini büyük ölçüde ortadan kaldırır.

Buna karşılık dayanıklılık gereksinimleri **taviz verilemez**: worker restart sonrası süreç kaybolmamalı, timer kalıcı olmalı, duplicate event tek side effect üretmeli, cross-tenant erişim engellenmeli, state + outbox + audit aynı transaction'da tutarlı olmalıdır.

## Değerlendirilen seçenekler

| Kriter | Custom (PostgreSQL-backed) | Temporal | Camunda 8 |
|---|---|---|---|
| MVP node seti için yeterlilik | **Yeterli** (6 node) | Fazlasıyla yeterli | Fazlasıyla yeterli |
| Durability | **Kanıtlanmalı** (spike konusu) | Kanıtlanmış | Kanıtlanmış |
| Human task semantiği | Domain'de doğal | Ek modelleme gerekir | Yerleşik |
| Transaction bütünlüğü (state+outbox+audit tek TX) | **Doğal** (aynı DB) | Zor (harici runtime, ayrı store) | Zor (harici runtime) |
| Multi-tenancy + RLS | **Doğal** (aynı DB, aynı politika) | Ek tasarım gerekir | Ek tasarım gerekir |
| Operasyon maliyeti (solo dev) | **Düşük** (ek altyapı yok) | Orta-yüksek (cluster/cloud) | **Yüksek** (Zeebe, broker, exporter) |
| Deployment karmaşıklığı | Düşük | Orta | Yüksek |
| Vendor lock-in | Yok | Orta | Yüksek |
| Maliyet | Yok | Cloud ücreti veya self-host | Lisans/altyapı |
| Ana risk | **Doğru yazmak zor; sessiz bug'lar kritik** | Öğrenme + operasyon | Ağırlık ve BPMN sürüklemesi |

**Camunda 8 elendi:** MVP node seti BPMN'in gücünü gerektirmiyor; Zeebe/broker/exporter operasyon yükü solo developer için orantısız; vendor lock-in yüksek.

**Temporal elenmedi, yedeğe alındı:** Durability problemini gerçekten çözüyor. Ancak state + outbox + audit'in **aynı PostgreSQL transaction'ında** tutulması FlowPilot'ın en kritik invariant'ı ve Temporal bunu doğal olarak vermiyor; ayrı bir durable store devreye giriyor.

## Karar

1. Workflow yürütme yeteneği **`WorkflowRuntimePort`** arkasına alınır. Uygulamanın geri kalanı somut runtime'ı bilmez.
2. Custom, hafif, **PostgreSQL-backed** runtime için **önce teknik spike** yapıldı ve **12/12 exit criterion geçti** (2026-07-19, commit `6cbbb7f`). Bkz. [workflow-runtime-spike-plan.md](../architecture/workflow-runtime-spike-plan.md) ve [workflow-runtime-spike-results.md](../architecture/workflow-runtime-spike-results.md).
3. **Kabul edilen runtime tasarımı** (spike ile kanıtlanan, production E09'a taşınacak kararlar):
   - **Custom PostgreSQL-backed runtime**, `WorkflowRuntimePort` arkasında (uygulama somut runtime'a bağımlı değildir).
   - **Transactional outbox** — state transition + outbox event + audit **aynı transaction'da** (dual write yok).
   - **PostgreSQL polling worker** — ayrı broker yok.
   - **`FOR UPDATE SKIP LOCKED`** + lease ile çoklu-worker güvenli claim.
   - **Idempotent inbox** (`processed_events`) — at-least-once teslim, duplicate side effect yok.
   - **Optimistic concurrency** — mutable aggregate'lerde `version` (+ approval için `UNIQUE(step_id)`).
   - **Persisted timers** — veritabanında; in-memory timer yasak.
   - **RLS tabanlı tenant izolasyonu** — her tenant tablosunda `tenant_id` + RLS ENABLE/FORCE; worker `NOBYPASSRLS`.
4. **Temporal**, ancak gelecekte bu kriterlerden biri bozulursa (veya yeniden değerlendirme tetikleyicileri gerçekleşirse) yeniden değerlendirilecek **yedek** olarak kalır; şu aşamada **gerekli değildir**.
5. **Camunda 8 MVP için elendi.**

## Gerekçe

- Dar node seti custom runtime'ı gerçekçi kılar.
- Aynı veritabanı; state + outbox + audit atomikliği ve RLS tabanlı tenant izolasyonu **doğal** olarak elde edilir.
- Ek altyapı bileşeni yok → solo developer için en düşük operasyon maliyeti.
- Port sınırı, spike başarısız olursa Temporal'a geçişi **domain kodunu yeniden yazmadan** mümkün kılar.

## Sonuçlar

**Pozitif**

- Tek veritabanı, tek transaction sınırı, düşük operasyon yükü.
- Vendor lock-in yok.
- Port sayesinde geri dönüş yolu açık.

**Negatif / risk**

- **Durable execution'ı doğru yazmak zordur.** Yanlış yazılmış bir runtime'ın hataları sessizdir ve veri bütünlüğünü bozar (kaybolan instance, çift onay, çift side effect).
- Bu risk, spike'ın **kanıt üretme zorunluluğu** ile yönetilir. Spike "çalışıyor gibi görünüyor" ile geçemez; her kriter için üretilmiş kanıt (test çıktısı, log, DB durumu) gerekir.

## Uyum kuralları (agent için bağlayıcı)

1. ~~Spike exit criteria geçmeden runtime'a bağlı kalıcı üretim kodu YASAK.~~ **Karşılandı (2026-07-19, 12/12).** Production runtime (E09) artık yazılabilir; §Karar/3'teki tasarım kararlarına uyar.
2. Uygulama katmanı yalnız `WorkflowRuntimePort` sözleşmesine bağımlıdır; somut runtime sınıflarına doğrudan bağımlılık YASAK.
3. Published workflow version **immutable**'dır; her instance tam olarak bir version'a bağlıdır.
4. Timer'lar veritabanında tutulur. In-memory timer YASAK.
5. State transition + outbox + audit **aynı transaction**'da yazılır.
6. Consumer'lar idempotenttir; "exactly once" iddiası YASAK.
7. Terminal instance yeni node başlatamaz.
8. MVP node seti dışında node tipi implemente edilemez.

## Yeniden değerlendirme tetikleyicileri

- Production runtime (E09) veya sonraki geliştirmelerde bu 12 kriterden **herhangi biri** regresyona uğrar ve düzeltilemezse → Temporal ADR'si açılır (Temporal yedek olarak korunur).
- Parallel/quorum/sub-workflow node'ları MVP sonrası kapsama girip custom runtime'ın karmaşıklığı yönetilemez hâle gelirse.
- Tenant başına instance hacmi PostgreSQL polling worker'ın ölçek sınırına dayanırsa.
- Tenant başına instance hacmi PostgreSQL polling worker'ın ölçek sınırına dayanırsa.
