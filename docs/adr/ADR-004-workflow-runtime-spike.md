# ADR-004 — Workflow Runtime: `WorkflowRuntimePort` Arkasında Custom PostgreSQL-Backed Runtime (Spike Şartına Bağlı)

- **Durum:** **Accepted (conditional)** — spike exit criteria'ya bağlı
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-003 (**koşullu**)
- **İlgili PRD bölümleri:** §9.7, §12, §26, §36.2, §36.3, §37, §38.6

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
2. Custom, hafif, **PostgreSQL-backed** runtime için **önce teknik spike** yapılır.
3. Spike'ın **12 exit criterion'unun tamamı** kanıtlanmadan runtime'a bağlı kalıcı üretim kodu yazılmaz. Bkz. [workflow-runtime-spike-plan.md](../architecture/workflow-runtime-spike-plan.md).
4. Spike **başarısız olursa** (bir veya daha fazla exit criterion kanıtlanamazsa) **Temporal yeniden değerlendirilir** ve bu ADR yeni bir ADR ile supersede edilir.
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

1. Spike exit criteria geçmeden **runtime'a bağlı kalıcı üretim kodu YASAK**.
2. Uygulama katmanı yalnız `WorkflowRuntimePort` sözleşmesine bağımlıdır; somut runtime sınıflarına doğrudan bağımlılık YASAK.
3. Published workflow version **immutable**'dır; her instance tam olarak bir version'a bağlıdır.
4. Timer'lar veritabanında tutulur. In-memory timer YASAK.
5. State transition + outbox + audit **aynı transaction**'da yazılır.
6. Consumer'lar idempotenttir; "exactly once" iddiası YASAK.
7. Terminal instance yeni node başlatamaz.
8. MVP node seti dışında node tipi implemente edilemez.

## Yeniden değerlendirme tetikleyicileri

- Spike exit criteria'dan **herhangi biri** kanıtlanamazsa → Temporal ADR'si açılır.
- Parallel/quorum/sub-workflow node'ları MVP sonrası kapsama girip custom runtime'ın karmaşıklığı yönetilemez hâle gelirse.
- Tenant başına instance hacmi PostgreSQL polling worker'ın ölçek sınırına dayanırsa.
