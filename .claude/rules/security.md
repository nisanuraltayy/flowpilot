# Güvenlik Kuralları

Bağlayıcı kaynak: PRD §9.1, §9.3, §9.19, §16, §17, §36.1 ve ADR-005, ADR-006.

Güvenlik, kaynak öncelik sırasının **en üstündedir**. Bir performans, UX veya teslim hızı gerekçesi güvenlik kuralını geçersiz kılamaz.

---

## 1. Tenant izolasyonu (en kritik risk)

**Invariant:** Hiçbir actor başka tenant'ın kaynağını okuyamaz veya değiştiremez.

**MUST:**

- Her tenant verisi taşıyan tablo `tenant_id` içerir.
- Tenant filtresi **geliştiricinin hatırlamasına bırakılamaz.** Filtre; repository/session boundary'sinde otomatik uygulanır ve ek savunma katmanı olarak PostgreSQL Row Level Security ile veritabanında zorlanır (ADR-006).
- `TenantContext` request/worker başlangıcında **bir kez** çözülür; handler'lar tenant kimliğini istemciden gelen gövde/parametreden okumaz.
- Cache key'leri tenant içerir. Search index sorguları tenant ile filtrelenir. Object storage yolları tenant ile ayrılır.
- Cross-tenant erişim denemesi **kaynağın varlığını sızdırmaz** (404 vs 403 ayrımı bilgi sızdırmayacak şekilde tasarlanır) ve güvenlik log'una yazılır.

**MUST NOT:**

- Ham SQL veya query builder ile tenant filtresi atlanamaz.
- Admin/servis rolü "kolaylık olsun" diye tenant filtresini bypass edemez.
- Tenant kimliği yalnızca frontend'den gelen değere güvenilerek belirlenemez.

**Test zorunluluğu:** Tenant verisine dokunan **her** story'de cross-tenant negatif test bulunur. Tenant A'nın actor'ü, Tenant B'nin kaynak ID'sini tahmin ederek erişemez.

---

## 2. Authentication boundary

- Authentication **managed provider** üzerinden yapılır (ADR-005). Provider seçimi **açık karardır**; gerçek entegrasyon owner kararı olmadan yapılmaz.
- Kullanıcı kimliği, organizasyon, membership, rol ve authorization **FlowPilot domain'inde** tutulur. Provider'ın organizasyon/rol modeline bağımlılık kurulmaz.
- Provider'dan gelen token **her istekte** doğrulanır (imza, issuer, audience, expiry). Token içindeki claim'ler doğrulanmadan yetki kaynağı olarak kullanılmaz.
- Provider'ın `sub` değeri FlowPilot `user` kaydına eşlenir. **E-posta adresi primary key olarak kullanılmaz.**
- Doğrulanmamış (e-posta doğrulaması tamamlanmamış) kullanıcı tenant verisine erişemez.

---

## 3. Authorization

- Authorization **merkezi policy boundary**'sindedir: `authorize(actor, action, resource)`.
- Controller içinde dağınık rol kontrolü **YASAK**.
- Her protected endpoint bir policy adı belirtir.
- Permission key'leri merkezi katalogda tanımlıdır (`workflow.definition.publish`, `approval.decide`, `audit.read`, ...).
- Yetkisiz butonu UI'da gizlemek **yeterli değildir**; backend enforcement zorunludur.
- Her authorization reddi güvenlik log'una yazılır.

**Onay güvenliği (PRD §36.1):**

- Onaycı yalnız kendisine veya rolüne atanmış **aktif** step üzerinde karar verebilir.
- Bir approval step için **tek geçerli aktif karar** bulunur; tekrar komutları idempotent sonuç döndürür (duplicate approval koruması: unique constraint + optimistic lock).
- Sıralı onayda ikinci step, birinci tamamlanmadan **aktif olmaz**.
- Self-approval politikası açıkken requester kendi adımını onaylayamaz.
- Karar veren actor'ün **karar anında** yetkili olduğu kanıtlanır ve audit'e yazılır.
- Kullanıcı başkasının hesabıyla onay tamamlayamaz.

**Test zorunluluğu:** Authorization içeren her story'de en az bir **negatif** test (yetkisiz actor reddedilir).

---

## 4. Koşul değerlendirme (condition evaluator)

- **YASAK:** `eval`, `exec`, dinamik Python/JavaScript çalıştırma, template engine üzerinden kod yürütme.
- **ZORUNLU:** Güvenli, deterministik expression DSL:
  - Sunucu tarafı parser
  - Whitelist edilmiş operatör ve fonksiyon seti
  - Tip kontrollü alan referansları
  - Maksimum expression karmaşıklığı
  - Evaluation timeout
  - Aynı girdi → aynı çıktı (deterministik)
  - Değerlendirme sonucu **açıklanabilir** olmalı ("Tutar 50.000 TL'den büyük olduğu için Finans onayı eklendi")

---

## 5. Audit log

- Audit log FlowPilot'ın **ürün bileşenidir**; application log'un yerine geçmez, application log da audit'in yerine geçmez.
- Audit **append-only**'dir. Update/delete YASAK. Düzeltme gerekiyorsa önceki olaya referans veren **correction event** yazılır.
- Audit event, business transaction başarısızsa yazılmaz. State transition + outbox + audit **aynı transaction** içinde tutarlı olur.
- Zorunlu alanlar: `event_id`, `tenant_id`, `actor_type`, `actor_id`, `action`, `resource_type`, `resource_id`, `timestamp` (UTC), `request_id`, `metadata`, `reason`.
- Kaydedilecek kritik aksiyonlar (ilk dilim): giriş, membership/rol değişimi, workflow publish, instance start, talep oluşturma, onay kararı, form verisi değişikliği, dosya yükleme/indirme, yetki reddi.
- Hassas değerlerin **tamamı** audit'e yazılmaz; maskeleme/hash uygulanır.

---

## 6. Veri sınıflandırması

| Sınıf | Örnek | Varsayılan kontrol |
|---|---|---|
| Public | Ürün dokümantasyonu | Normal erişim |
| Internal | Workflow template metadata | Tenant + auth |
| Confidential | Form cevapları, görevler, talepler | Tenant + resource authorization |
| Restricted | Kimlik, finansal alanlar | Field-level policy, minimum log |
| Secret | Token, API key, encryption key | Secret manager; gösterilmez, rotate edilir |

- Restricted/Secret veriler **log'a yazılmaz** (redaction zorunlu).
- Hassas alanlar varsayılan olarak index'lenmez ve export'a dahil edilmez.
- Gereksiz PII toplanmaz (privacy by design/default — KVKK).

---

## 7. Secret yönetimi

- **YASAK:** Secret, token, API key, connection string veya kişisel veri commit etmek.
- `.env` dosyaları commit edilmez; yalnız secret içermeyen `.env.example` bulunur.
- Agent uydurma environment variable veya sahte credential üretmez.
- Production credential agent'e verilmez; yalnız ephemeral sandbox/staging credential kullanılır.
- Her commit'te secret scan çalışır.

---

## 8. Girdi, dosya ve dış çağrı

- Sunucu tarafı validation **zorunludur**; UI validation bypass edilebilir kabul edilir.
- Mass assignment YASAK: istemciden gelen gövde doğrudan entity'ye map edilmez.
- Dosya yükleme presigned URL ile yapılır; dosya içeriği API process memory'sinden geçirilmez. MIME/boyut policy uygulanır. Zararlı içerik taraması için entegrasyon noktası bırakılır; tarama tamamlanmadan restricted dosya indirilemez.
- Her dış HTTP çağrısı timeout, bounded retry ve telemetry içerir.
- Tüm liste endpoint'leri cursor pagination ve server-side max page size kullanır (DoS koruması).

---

## 9. Güvenlik kapıları

Aşağıdakiler **kapatılamaz, atlanamaz veya "geçici olarak" devre dışı bırakılamaz**:

- Cross-tenant test suite
- Negative authorization test suite
- Secret scan
- Dependency vulnerability scan
- Pre-commit güvenlik hook'ları

Açık **critical/high** finding varken story done sayılamaz.
