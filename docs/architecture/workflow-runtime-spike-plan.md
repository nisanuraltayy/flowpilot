# Workflow Runtime Spike Planı

İlgili ADR: [ADR-004](../adr/ADR-004-workflow-runtime-spike.md). İlgili PRD bölümleri: §9.7, §36.2, §36.3, §37, §38.6.

> **Bu bir plandır. Spike kodu henüz yazılmamıştır ve owner onayı olmadan yazılmayacaktır.**

---

## 1. Spike'ın amacı

Custom, hafif, **PostgreSQL-backed** workflow runtime'ın; FlowPilot'ın dayanıklılık, tutarlılık ve izolasyon gereksinimlerini **kanıtlanabilir şekilde** karşılayıp karşılayamadığını belirlemek.

Bu bir "çalışıyor gibi görünüyor" doğrulaması **değildir**. Her kriter için üretilmiş **kanıt** (otomatik test çıktısı, veritabanı durumu, log) gerekir.

**Spike başarısız olursa:** Temporal yeniden değerlendirilir ve ADR-004 yeni bir ADR ile supersede edilir. Bu, kabul edilebilir ve planlanmış bir sonuçtur — spike'ın amacı bu kararı **ucuz** vermektir.

## 2. Spike sınırları

**Kapsam içi:** MVP node seti (`Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`), instance yaşam döngüsü, persisted timer, transactional outbox, idempotent inbox, optimistic concurrency, tenant izolasyonu.

**Kapsam dışı:** Parallel split/join, quorum, sub-workflow, script/webhook/AI node, DMN, görsel canvas, SLA/eskalasyon zinciri, gerçek auth provider entegrasyonu, üretim kalitesinde UI.

**Spike kodu üretim kodu değildir.** Ayrı bir dizinde/branch'te yaşar, `main`'e üretim kodu olarak merge edilmez. Çıktısı **karar ve kanıttır**, ürün değildir.

## 3. Test edilecek referans akış

Tüm kriterler tek bir referans akış üzerinde doğrulanır:

```text
Start → Form (satın alma talebi) → Condition (tutar) → Sequential Approval → Notification → End
                                          │
                                          ├─ tutar ≤ 10.000 TL  → 1 adımlı onay (ekip yöneticisi)
                                          └─ tutar >  10.000 TL → 2 adımlı sıralı onay (ekip yöneticisi → finans)
```

Tutarlar minor unit (kuruş) + `TRY` olarak modellenir.

---

## 4. Exit criteria

Aşağıdaki **12 kriterin tamamı** kanıtlanmadan spike başarılı sayılamaz ve runtime'a bağlı üretim kodu yazılamaz. Kısmi başarı → başarısızlık.

---

### SPK-01 — Published workflow version immutable

- **Amaç:** Yayınlanmış bir workflow version'ın hiçbir yolla değiştirilemediğini kanıtlamak. Bu, devam eden süreçlerin güvenliğinin temelidir.
- **Test senaryosu:** Bir workflow yayınlanır (`v1`), hash'i kaydedilir. (a) Uygulama katmanından version güncellemesi denenir. (b) Aynı workflow'dan yeni draft oluşturulup düzenlenir ve `v2` yayınlanır. (c) `v1` kaydı ve hash'i yeniden okunur.
- **Test türü:** Integration (DB + uygulama katmanı) + fitness check (statik analiz).
- **Beklenen sonuç:** (a) Domain hatası ile reddedilir. (b) `v2` ayrı bir kayıt olarak oluşur. (c) `v1`'in içeriği ve hash'i **bit düzeyinde değişmemiştir**. Kod tabanında published tablolarına `UPDATE` çalıştıran hiçbir yol yoktur.
- **Başarısızlık koşulu:** `v1` içeriği veya hash'i değişirse; ya da published kayda `UPDATE` çalıştıran bir kod yolu bulunursa.
- **Teknik risk:** ORM'in "dirty" nesneyi otomatik flush etmesi. Uygulama katmanında engellenen mutasyonun ham SQL ile hâlâ mümkün olması.
- **Üretilmesi gereken kanıt:** Test çıktısı + publish öncesi/sonrası hash karşılaştırması + fitness check raporu (`UPDATE` yolu bulunamadı).
- **Exit criterion:** Published version'ı değiştiren **hiçbir** kod yolu yok; hash sabit.

---

### SPK-02 — Instance belirli bir workflow version'a bağlı

- **Amaç:** Bir instance başladıktan sonra workflow değişse bile, o instance'ın **başladığı** version ile ilerlediğini kanıtlamak (PRD §36.1/4).
- **Test senaryosu:** `v1` ile bir instance başlatılır ve onay adımında bekletilir. Workflow düzenlenip `v2` yayınlanır (`v2`'de koşul eşiği ve onay zinciri değiştirilir). Bekleyen instance ilerletilir. Ardından yeni bir instance başlatılır.
- **Test türü:** Integration.
- **Beklenen sonuç:** Bekleyen instance **`v1` semantiğiyle** tamamlanır; `v2`'nin yeni eşiğinden etkilenmez. Yeni instance varsayılan olarak `v2` kullanır. Her instance kaydı bağlı olduğu `workflow_version_id`'yi taşır.
- **Başarısızlık koşulu:** Devam eden instance `v2` kurallarıyla ilerlerse veya version referansı bulanıklaşırsa (örn. "son yayınlanan" dinamik olarak çözülüyorsa).
- **Teknik risk:** Runtime'ın node tanımını `workflow_id` üzerinden "en güncel version"ı çözerek okuması — sessiz ve yıkıcı bir hata sınıfı.
- **Üretilmesi gereken kanıt:** İki instance'ın farklı version'larla farklı yollardan tamamlandığını gösteren test çıktısı + DB'de `workflow_version_id` referansları.
- **Exit criterion:** Devam eden instance yeni yayından **etkilenmez**.

---

### SPK-03 — Condition node doğru branch'i seçiyor

- **Amaç:** Güvenli, deterministik condition evaluator'ın doğru branch'i seçtiğini ve `eval` kullanmadığını kanıtlamak.
- **Test senaryosu:** Sınır değerleri dahil parametrik testler: 9.999,99 TL / 10.000,00 TL / 10.000,01 TL. Ayrıca: eksik alan, `null` tutar, yanlış tip (string), farklı para birimi, zararlı ifade denemesi (`__import__("os").system(...)` benzeri bir payload).
- **Test türü:** Unit (evaluator) + integration (runtime içinde branch seçimi).
- **Beklenen sonuç:** Sınır değerlerinde doğru branch. Eksik/yanlış tip → kontrollü validation hatası (crash değil, sessiz `false` değil). Zararlı ifade → parser tarafından reddedilir, **çalıştırılmaz**. Aynı girdi her zaman aynı çıktı. Seçim gerekçesi açıklanabilir ("tutar > 10.000 TL").
- **Başarısızlık koşulu:** Sınır değerinde yanlış branch; herhangi bir kod çalıştırma yolu; aynı girdinin farklı çıktı üretmesi.
- **Teknik risk:** Kolaylık uğruna `eval`/`exec` veya bir template engine'e kayma. Ondalık/float yuvarlama hatası (bu yüzden minor unit zorunlu).
- **Üretilmesi gereken kanıt:** Sınır değer test tablosu + zararlı payload'ın reddedildiğini gösteren test + evaluator'ın açıklama çıktısı.
- **Exit criterion:** Deterministik, güvenli (kod çalıştırmayan), açıklanabilir evaluator.

---

### SPK-04 — Sıralı onayda ikinci adım birinci tamamlanmadan aktif olmuyor

- **Amaç:** Sequential approval'ın gerçekten sıralı olduğunu kanıtlamak.
- **Test senaryosu:** 2 adımlı onay zinciri (yönetici → finans) aktifleşir. (a) Finans onaycısı, birinci adım henüz bekliyorken doğrudan karar vermeye çalışır. (b) Yönetici onaylar. (c) Finans onaycısı tekrar dener.
- **Test türü:** Integration (API + DB).
- **Beklenen sonuç:** (a) `403`/`409` ile reddedilir; **hiçbir karar kaydı oluşmaz**; step `pending` kalır; yetki reddi audit'e yazılır. (b) İkinci step `pending → active` olur; instance hâlâ `waiting`. (c) Şimdi karar kabul edilir; instance ilerler.
- **Başarısızlık koşulu:** İkinci adımın erken karar kabul etmesi; ya da birinci onay sonrası ikinci adımın aktifleşmemesi (süreç asılı kalır).
- **Teknik risk:** Step aktivasyonunun event handler'da yapılıp transaction dışında kalması → onay verilir ama sonraki adım hiç aktifleşmez (sessiz asılı süreç).
- **Üretilmesi gereken kanıt:** Erken karar denemesinin reddedildiğini gösteren test çıktısı + `approval_steps` durum geçiş tablosu + audit kaydı.
- **Exit criterion:** Sıra atlanamıyor **ve** sıra asılı kalmıyor.

---

### SPK-05 — Aynı approval command iki kez gönderildiğinde tek karar oluşuyor

- **Amaç:** Duplicate approval koruması (çift tıklama, iki sekme, retry).
- **Test senaryosu:** Aynı approval step için aynı actor'den **eşzamanlı** iki karar komutu gönderilir (paralel iki istek, aynı idempotency key). Ayrıca: aynı komut sıralı olarak iki kez gönderilir. Ayrıca: iki **farklı** onaycı aynı step için eşzamanlı karar verir.
- **Test türü:** Integration + concurrency (paralel istek).
- **Beklenen sonuç:** `approval_decisions` tablosunda **tam olarak bir** kayıt oluşur. İkinci istek ya aynı sonucu idempotent olarak döner ya da `409` alır — ama **ikinci bir karar yaratmaz**. Workflow **bir kez** ilerler; iki notification/iki task oluşmaz.
- **Başarısızlık koşulu:** İki karar kaydı; iki state transition; çift notification; ya da veritabanı deadlock'u ile isteğin çökmesi.
- **Teknik risk:** Uygulama seviyesinde "önce oku, yoksa yaz" kontrolü yarış koşuluna açıktır. Koruma **veritabanı düzeyinde** olmalıdır (unique constraint + optimistic lock).
- **Üretilmesi gereken kanıt:** Paralel istek testi çıktısı + `approval_decisions` satır sayısı = 1 + outbox'ta tek event.
- **Exit criterion:** Eşzamanlı duplicate komut → **tek** karar, **tek** state transition, **tek** side effect.

---

### SPK-06 — Aynı outbox event iki kez işlendiğinde duplicate side effect oluşmuyor

- **Amaç:** At-least-once teslimin idempotent consumer ile güvenli olduğunu kanıtlamak (PRD §37.2, §37.4).
- **Test senaryosu:** Bir `approval.decided.v1` event'i dispatcher tarafından işlenir. Ardından **aynı event** (aynı `event_id`) yeniden dispatch edilir — worker crash'i sonrası yeniden teslim simülasyonu. Ayrıca iki worker aynı anda aynı event'i almaya çalışır.
- **Test türü:** Integration + resilience.
- **Beklenen sonuç:** İkinci işleme **hiçbir** yeni side effect üretmez: tek notification, tek task, tek audit kaydı, tek state transition. `processed_events` (inbox) kaydı ikinci işlemeyi engeller. İki worker senaryosunda `SKIP LOCKED` ile yalnız biri işler.
- **Başarısızlık koşulu:** İkinci bildirim; ikinci task; ikinci audit kaydı; ya da instance'ın iki kez ilerlemesi.
- **Teknik risk:** Idempotency kontrolünün side effect'ten **sonra** yapılması. Inbox kaydının side effect ile farklı transaction'da yazılması (arada crash → duplicate).
- **Üretilmesi gereken kanıt:** Duplicate dispatch testi + side effect tablolarında satır sayısı sabit + `processed_events` kaydı.
- **Exit criterion:** Duplicate event **hiçbir** duplicate side effect üretmiyor.

---

### SPK-07 — Worker kapanıp açıldığında süreç kaybolmuyor

- **Amaç:** Durable execution'ın temel iddiasını kanıtlamak.
- **Test senaryosu:** Referans akış çalışırken worker process **zorla öldürülür** (`SIGKILL`, graceful shutdown değil) — bir event işlenmenin tam ortasındayken. Worker yeniden başlatılır. Süreç tamamlanmaya bırakılır. Senaryo: (a) outbox'a yazıldı ama dispatch edilmedi, (b) dispatch başladı ama tamamlanmadı.
- **Test türü:** Resilience / e2e (gerçek process kill).
- **Beklenen sonuç:** Worker yeniden başladığında işlenmemiş outbox event'lerini alır ve süreç **doğru şekilde** tamamlanır. Hiçbir instance `running`/`waiting` durumunda kalıcı olarak asılı kalmaz. Yarım işlenmiş event duplicate side effect üretmez (SPK-06 ile birlikte).
- **Başarısızlık koşulu:** Süreç kaybolur (instance asılı kalır); ya da restart sonrası duplicate side effect oluşur.
- **Teknik risk:** Event'in "işleniyor" olarak işaretlenip crash sonrası hiç geri alınmaması (kayıp event). Lease/visibility timeout'un olmaması.
- **Üretilmesi gereken kanıt:** Kill/restart testinin otomatik çıktısı + restart öncesi/sonrası instance state + son durumun `completed` olduğu.
- **Exit criterion:** `SIGKILL` sonrası süreç **kayıpsız ve duplicate'siz** tamamlanıyor.

---

### SPK-08 — Persisted timer restart sonrasında çalışmaya devam ediyor

- **Amaç:** Timer'ların veritabanında yaşadığını ve process ömrüne bağlı olmadığını kanıtlamak (in-memory timer YASAK).
- **Test senaryosu:** Kısa süreli bir timer (örn. onay hatırlatması) planlanır. Timer ateşlenmeden **önce** worker öldürülür. Fake clock ile zaman ileri alınır. Worker yeniden başlatılır.
- **Test türü:** Integration + resilience (fake clock ile).
- **Beklenen sonuç:** Timer `timers` tablosunda persist edilmiştir. Worker yeniden başladığında vadesi gelmiş timer'ı bulur ve **tam olarak bir kez** ateşler. Timer gecikmesi (planlanan vs gerçek ateşleme) metrik olarak ölçülebilir.
- **Başarısızlık koşulu:** Timer restart sonrası kaybolur; ya da iki kez ateşlenir; ya da timer yalnız bellekte tutulmuştur.
- **Teknik risk:** Scheduler kütüphanesinin timer'ı bellekte tutması. Çoklu worker'da aynı timer'ın iki kez ateşlenmesi (lease yok).
- **Üretilmesi gereken kanıt:** `timers` tablosunun restart öncesi/sonrası durumu + tek ateşleme kanıtı + gecikme metriği.
- **Exit criterion:** Timer restart'tan sağ çıkıyor ve **tam bir kez** ateşleniyor.

---

### SPK-09 — Terminal instance yeni node başlatamıyor

- **Amaç:** Terminal state guard'ının varlığını kanıtlamak (PRD §36.1/5).
- **Test senaryosu:** Bir instance `completed` (ve ayrıca `rejected`, `cancelled`) durumuna getirilir. Sonra: (a) gecikmeli bir outbox event'i bu instance'a ilerleme komutu gönderir, (b) bir kullanıcı iptal edilmiş instance'ın açık görünen onay adımına karar vermeye çalışır, (c) geciken bir timer ateşlenir.
- **Test türü:** Integration.
- **Beklenen sonuç:** Üç durumda da komut **kontrollü şekilde reddedilir**; yeni node execution oluşmaz; yeni task/notification üretilmez. Reddin **crash değil**, tanımlı bir domain hatası olması gerekir. Instance cancel edildiğinde açık task/approval/timer'lar `cancelled` olarak kapatılmıştır.
- **Başarısızlık koşulu:** Terminal instance'ta yeni node execution oluşması; ya da geciken bir event'in tamamlanmış süreci "dirilterek" ilerletmesi.
- **Teknik risk:** Terminal kontrolünün yalnız API katmanında olması; event handler'ın (arka kapı) kontrolü atlaması.
- **Üretilmesi gereken kanıt:** Üç senaryonun test çıktısı + terminal instance'ta `node_executions` satır sayısının değişmediği.
- **Exit criterion:** Terminal instance **hiçbir yoldan** (API, event, timer) ilerletilemiyor.

---

### SPK-10 — Cross-tenant actor başka tenant'ın instance'ına erişemiyor

- **Amaç:** Tenant izolasyonunun runtime katmanında da geçerli olduğunu kanıtlamak (ADR-006).
- **Test senaryosu:** Tenant A ve Tenant B oluşturulur. Tenant B'de bir instance ve bir aktif approval step yaratılır; ID'leri alınır. Tenant A'nın actor'ü şunları dener: (a) instance'ı okumak, (b) instance'ı iptal etmek, (c) approval step'e karar vermek, (d) timeline/audit okumak, (e) ekli dosyayı indirmek. Ayrıca RLS'in tek başına çalıştığını doğrulamak için uygulama filtresi bilinçli olarak kaldırılmış bir sorgu çalıştırılır.
- **Test türü:** Security (integration) — cross-tenant / IDOR-BOLA suite.
- **Beklenen sonuç:** Beş denemenin **tamamı** reddedilir. Kaynağın varlığı sızdırılmaz. Her deneme güvenlik log'una yazılır. Uygulama filtresi kaldırılsa bile **RLS sorguyu boş döndürür** (ikinci savunma katmanı kanıtlanır).
- **Başarısızlık koşulu:** Herhangi bir denemede veri sızması; ya da RLS'in devre dışı olduğunun ortaya çıkması; ya da worker'ın `BYPASSRLS` rolüyle çalışması.
- **Teknik risk:** Worker/dispatcher'ın tenant context olmadan çalışması ve RLS'i bypass eden bir rol kullanması — **en sinsi sızıntı yolu budur.**
- **Üretilmesi gereken kanıt:** Cross-tenant test suite çıktısı (5/5 reddedildi) + RLS'in filtresiz sorguyu boşa düşürdüğünü gösteren kanıt + worker'ın RLS'e tabi olduğu kanıtı.
- **Exit criterion:** Cross-tenant erişim **iki bağımsız katman** tarafından da engelleniyor.

---

### SPK-11 — State transition, outbox ve audit aynı transaction içinde tutarlı

- **Amaç:** Dual write'ın olmadığını; state, event ve audit'in atomik olduğunu kanıtlamak (PRD §36.1/13, ADR-007).
- **Test senaryosu:** Bir onay kararı işlenirken, transaction commit'inden **hemen önce** yapay bir hata enjekte edilir (fault injection). Ardından hata kaldırılıp işlem tekrarlanır. Ayrıca outbox handler'ın side effect'i başarısız olduğu senaryo denenir.
- **Test türü:** Integration + fault injection.
- **Beklenen sonuç:** Hata enjekte edildiğinde: **hiçbiri** yazılmaz — ne karar, ne state değişikliği, ne outbox event'i, ne audit kaydı. Kısmi durum oluşmaz. Kullanıcıya başarı dönülmez. Tekrar denendiğinde üçü birlikte yazılır. Side effect başarısızlığı ise state'i geri almaz ama incident/retry üretir ve kullanıcıdan gizlenmez.
- **Başarısızlık koşulu:** Audit yazılmış ama business state yazılmamış (veya tersi); outbox event'i yazılmış ama state yazılmamış (veya tersi); kullanıcıya başarı dönülmüş ama commit olmamış.
- **Teknik risk:** Audit'in "temizlik olsun" diye ayrı bir session/transaction'da yazılması. Outbox event'inin `after_commit` hook'unda yazılması (= dual write).
- **Üretilmesi gereken kanıt:** Fault injection testi çıktısı + rollback sonrası dört tablonun da boş olduğu (`approval_decisions`, instance state, `outbox_events`, `audit_events`).
- **Exit criterion:** Ya **hepsi** yazılır ya **hiçbiri**. Kısmi durum yok.

---

### SPK-12 — Optimistic concurrency conflict kontrollü hata üretiyor

- **Amaç:** Eşzamanlı yazımların "son yazan kazanır" ile sessizce veri kaybetmediğini kanıtlamak (PRD §37.3).
- **Test senaryosu:** Aynı workflow draft (ve ayrıca aynı task, aynı instance) iki actor tarafından aynı `version` değeri okunarak eşzamanlı güncellenir. Ayrıca iki worker aynı instance'ı aynı anda ilerletmeye çalışır.
- **Test türü:** Integration + concurrency.
- **Beklenen sonuç:** Bir yazma başarılı olur; diğeri **`409 Conflict`** (veya `412`) ile **kontrollü** reddedilir. Sessiz üzerine yazma **yok**. Veri kaybı **yok**. Worker çakışmasında biri geri çekilir ve retry eder; instance state bozulmaz. Hata mesajı kullanıcıya anlamlıdır.
- **Başarısızlık koşulu:** İkinci yazmanın birinciyi sessizce ezmesi; ya da conflict'in yakalanmamış bir exception/500 olarak patlaması; ya da deadlock.
- **Teknik risk:** `version` alanının bazı aggregate'lerde unutulması. Worker'ın conflict'i sonsuz retry ile döngüye sokması (bounded retry zorunlu).
- **Üretilmesi gereken kanıt:** Eşzamanlı yazma testi çıktısı + `409` yanıtı + kaybolmamış veri kanıtı + retry'ın bounded olduğu.
- **Exit criterion:** Conflict **kontrollü** hata üretiyor; sessiz veri kaybı yok.

---

## 5. Exit criteria özeti

| # | Kriter | Ana risk |
|---|---|---|
| SPK-01 | Published version immutable | ORM auto-flush |
| SPK-02 | Instance version'a bağlı | "Son version"ı dinamik çözme |
| SPK-03 | Condition doğru branch | `eval` kayması, float yuvarlama |
| SPK-04 | Sıralı onay sırası korunuyor | Asılı kalan step |
| SPK-05 | Duplicate approval → tek karar | Uygulama seviyesinde yarış koşulu |
| SPK-06 | Duplicate event → tek side effect | Idempotency side effect'ten sonra |
| SPK-07 | Worker restart → süreç kayıpsız | Kayıp/asılı event lease'i |
| SPK-08 | Persisted timer restart'tan sağ çıkıyor | In-memory scheduler |
| SPK-09 | Terminal instance ilerletilemiyor | Event handler'ın guard'ı atlaması |
| SPK-10 | Cross-tenant erişim engelli | Worker'ın RLS'i bypass etmesi |
| SPK-11 | State + outbox + audit atomik | Audit/outbox'ın ayrı transaction'da olması |
| SPK-12 | Concurrency conflict kontrollü | Eksik `version` alanı, sessiz overwrite |

**Spike başarılı sayılır ancak ve ancak 12/12 kriter kanıtlanmışsa.**

## 6. Spike çıktıları

1. **Kanıt paketi** — her kriter için otomatik test çıktısı, DB durumu ve log.
2. **Spike raporu** — hangi kriter nasıl kanıtlandı; hangi zorluklar çıktı; hangi kod yaklaşımı işe yaradı.
3. **ADR-004 güncellemesi** — `Accepted (conditional)` → `Accepted` (12/12 geçti) **veya** yeni ADR ile Temporal'a geçiş.
4. **Runtime tasarım notu** — üretim implementasyonuna taşınacak tasarım kararları (lease mekanizması, inbox tablosu şeması, guard'ların yeri).
5. Spike sırasında keşfedilen varsayımlar → `docs/assumptions.md`; açık kararlar → `docs/open-questions.md`.

## 7. Başarısızlık protokolü

Bir kriter kanıtlanamazsa:

1. Sorunun **temel** mi (yaklaşımın kendisi yanlış) yoksa **düzeltilebilir** mi (implementasyon hatası) olduğu belirlenir.
2. Düzeltilebilirse spike içinde düzeltilir ve kriter yeniden çalıştırılır.
3. Temel bir sınırsa → spike durdurulur, bulgu raporlanır, **Temporal ADR'si açılır**. Bu bir başarısızlık değil, **ucuza alınmış doğru karardır**.
4. Hiçbir koşulda kriter "yeterince yakın" diye geçmiş sayılamaz veya sessizce kapsam dışına alınamaz.
