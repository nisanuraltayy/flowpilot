# Varsayım Günlüğü (Assumptions)

Agent, belirsizlikte rastgele karar vermek yerine varsayımı buraya kaydeder (PRD §33.3, §45.3).

**Kural:** Yüksek etkili **ve** geri döndürülemez varsayımlar implementasyona çevrilmez; ADR veya owner kararı bekler.

Format:

```yaml
- id: ASM-XXXX
  statement: "..."
  impact: low | medium | high
  reversible: true | false
  owner: product | engineering | security | legal
  status: unvalidated | validated | rejected
  validation_method: "..."
  expires_at: YYYY-MM-DD
  affected_stories: [FP-Exx-000]
```

---

## Aktif varsayımlar

```yaml
- id: ASM-0001
  statement: >
    Satın alma onay eşikleri, demo ve ilk dikey dilim için GEÇİCİ ÜRÜN VARSAYIMI olarak
    owner tarafından şu şekilde belirlenmiştir:
      - 10.000 TL altı            → ekip yöneticisi (1 adım)
      - 10.000 – 50.000 TL arası  → ekip yöneticisi → finans (2 adım)
      - 50.000 TL üzeri           → ekip yöneticisi → finans → genel müdür (3 adım)
    Bu değerler gerçek müşteri verisiyle DOĞRULANMAMIŞTIR.
  impact: low
  reversible: true
  owner: product
  status: unvalidated
  validation_method: "Pilot müşteri görüşmesi (PRD §29): 'Onay limitleri nasıl belirleniyor?'"
  expires_at: 2026-10-01
  affected_stories: [FP-E09-003, FP-E10-002, FP-E15-001]
  binding_rule: >
    MUST NOT: Bu eşikler ve kademe sayısı domain koduna HARD-CODE EDİLEMEZ.
    Eşikler workflow definition içindeki Condition node koşullarından gelir;
    onay zinciri Sequential Approval node config'inden okunur.
    Eşiği değiştirmek = yeni bir workflow version yayınlamak. Kod değişikliği DEĞİL.
  design_consequence: >
    Sequential Approval node'u 1, 2 VEYA 3 adımlı zincirleri desteklemek zorundadır.
    Kademe sayısı config'ten gelir; sabit değildir. Condition evaluator iki eşikli
    (10.000 ve 50.000) dallanmayı desteklemelidir.
  reference: docs/product/mvp-scope-v0.1.md#6-satın-alma-onay-eşikleri-geçici-ürün-varsayımı

- id: ASM-0002
  statement: >
    İlk dikey dilimde para birimi tenant varsayılanı (TRY) ile sınırlıdır. Money value
    object'i çoklu para birimini destekler ancak kur çevrimi ve çoklu para biriminde
    onay eşiği karşılaştırması MVP'de yoktur.
  impact: medium
  reversible: true
  owner: product
  status: unvalidated
  validation_method: "Pilot müşteriler döviz bazlı satın alma yapıyor mu?"
  expires_at: 2026-10-01
  affected_stories: [FP-E02-003, FP-E06-001, FP-E09-003]
  note: >
    Farklı para birimlerinde tutar karşılaştırması domain hatası fırlatır — sessizce
    dönüştürmez. Bu, yanlış onay yönlendirmesini engeller.

- id: ASM-0003
  statement: >
    İlk dikey dilimde onaycı çözümleme yalnız "belirli kullanıcı" ve "belirli rol"
    stratejilerini destekler. "Talep sahibinin yöneticisi" (manager hierarchy) stratejisi
    MVP dışıdır; satın alma şablonu rol bazlı onaycı kullanır.
  impact: medium
  reversible: true
  owner: product
  status: unvalidated
  validation_method: "KOBİ'lerde onay zinciri role mi kişiye mi bağlı yürüyor?"
  expires_at: 2026-10-01
  affected_stories: [FP-E11-002, FP-E10-001, FP-E15-001]
  note: >
    Manager hierarchy eklendiğinde assignee resolution stratejisi genişletilir;
    Strategy pattern bu genişlemeyi domain kodunu değiştirmeden mümkün kılar.

- id: ASM-0004
  statement: >
    "Purchase Request" ayrı bir bounded context/modül olarak konumlandırılmıştır.
    PRD §35.1'in bounded context tablosunda ayrı bir context olarak listelenmemiştir;
    ancak ilk dikey dilim satın alma talebi olduğu ve talep kendi aggregate'i, kendi
    tablosu ve kendi yaşam döngüsü olan bir domain kavramı olduğu için ayrı modül
    olarak modellenmiştir.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    İkinci süreç (izin talebi) eklendiğinde: "Request" genel bir context mi olmalı,
    yoksa her süreç kendi context'i mi? Modül sınırı o zaman netleşir.
  expires_at: 2026-12-01
  affected_stories: [FP-E06-001, FP-E06-002, FP-E06-003]
  note: >
    Alternatif: talep, Form Submission + Workflow Instance'ın türevi olarak modellenip
    ayrı modül açılmayabilirdi. Bu durumda ikinci süreç eklendiğinde generic bir
    "Request" kavramı ortaya çıkar. Şu anki tercih daha açık (explicit) olduğu için seçildi.

- id: ASM-0011
  statement: >
    Bounded context'lerin domain/application/infrastructure alt paketleri henüz
    OLUŞTURULMADIĞI için, katman bazlı import kuralları (domain FastAPI/SQLAlchemy
    import edemez; cross-context domain/infrastructure importu yasak; composition root
    domain/infrastructure'a erişemez) import-linter ile HENÜZ ifade edilemiyor —
    grimp var olmayan modülü çözemez.
    Kontrol sessizce kaldırılmadı: aynı kurallar salt-okunur bir AST script'i ile
    zorlanıyor (scripts/check_import_boundaries.py) ve script'in üç ihlal sınıfını da
    yakaladığı sahte bir ihlal ağacına karşı kanıtlandı.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    İlk bounded context'in domain/application/infrastructure paketleri oluştuğunda
    (E01/E02 story'leri) kuralların import-linter contract'larına taşınması denenecek.
    Taşınabilirse AST script'i kaldırılır; taşınamazsa script kalıcı kontrol olur.
  expires_at: 2026-10-01
  affected_stories: [FP-E01-002, FP-E02-001]
  note: >
    Şu an import-linter 4 contract zorluyor (katman sırası, api/worker bağımsızlığı,
    shared saflığı, modules'ün web framework'e bağımlı olamaması). Eksik olan YALNIZ
    context içi katman kurallarıdır; onlar da AST ile zorlanıyor. İki aracın birlikte
    çalışması geçici bir durumdur, kalıcı tasarım değildir.

- id: ASM-0012
  statement: >
    organization_memberships.user_id, identity_users tablosuna işaret eder ancak
    veritabanı düzeyinde CROSS-MODULE FOREIGN KEY TANIMLANMAMIŞTIR. Actor'ün
    varlığı application katmanında, identity'nin açık cross-module contract'ı
    (UserDirectory.exists) ile doğrulanır.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    Membership lifecycle story'lerinde (FP-E03-001) yeniden değerlendirilir:
    kullanıcı silme/deaktivasyon senaryoları geldiğinde referential integrity
    ihtiyacı netleşecek.
  expires_at: 2026-10-01
  affected_stories: [FP-E02-001, FP-E03-001]
  note: >
    Gerekçe: DB-level FK, identity ve organization modüllerini şema düzeyinde
    birbirine kilitler ve ileride modül ayrılabilirliğini (ADR-003 strangler)
    bozar. Maliyet: DB, var olmayan bir user_id'li membership'i engellemez —
    bu koruma application katmanındadır. Tenant_id FK'sı ise modül İÇİ olduğu
    için DB düzeyinde tutulmuştur.

- id: ASM-0006
  statement: >
    Dosya eki için S3-compatible storage portu MVP'de MinIO (local development) üzerinde
    doğrulanır; production'da hangi S3-compatible sağlayıcının kullanılacağı hosting
    kararına (LOCK-006, OQ-002) bağlıdır.
  impact: low
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: "Hosting kararı verildiğinde sağlayıcı seçilir."
  expires_at: 2026-10-01
  affected_stories: [FP-E06-003]
  note: "Port sayesinde sağlayıcı değişimi adapter değişikliğinden ibarettir."

- id: ASM-0007
  statement: >
    Gerçek malware/zararlı içerik taraması Local MVP'de IMPLEMENTE EDİLMEZ.
    MalwareScanPort tasarlanır; MVP'de yalnız no-op/stub adapter bulunur.
    scan_status alanı ve tarama tamamlanmadan indirmeyi engelleyen kapı ŞİMDİDEN hazırdır.
  impact: high
  reversible: true
  owner: security
  status: validated
  validation_method: "Owner kararı: Local MVP çıkış kriteri DEĞİL; pilot-ready ZORUNLU güvenlik çıkış kriteri."
  expires_at: 2026-11-01
  affected_stories: [FP-E06-003]
  binding_rule: >
    Gerçek tarama entegrasyonu PILOT-READY sürümün zorunlu güvenlik çıkış kriteridir.
    Local MVP pilot müşteriye AÇILMAZ. Gerçek müşteri verisi işlenmeden önce tarama
    entegre edilmiş olmalıdır.
  reference: docs/product/mvp-scope-v0.1.md#4-pilot-ready-çıkış-kriterleri

- id: ASM-0010
  statement: >
    Local MVP'de e-posta bildirimi YOKTUR (yalnız in-app). Onaycının bekleyen onayı
    fark etmesi, uygulamaya girmesine bağlıdır.
  impact: medium
  reversible: true
  owner: product
  status: validated
  validation_method: "Owner kararı: e-posta MVP dışı, pilot-ready kapsamında."
  expires_at: 2026-10-01
  affected_stories: [FP-E12-001]
  binding_rule: >
    NotificationChannelPort ŞİMDİDEN provider-neutral (kanal-nötr) tasarlanır.
    MVP'de yalnız in-app adapter uygulanır. E-posta eklemek bir ADAPTER eklemek olmalıdır,
    bir refactor DEĞİL.
  risk_note: >
    PRD'nin ana problem tanımı "onaylar e-postada dağılıyor". E-posta olmadan onaycı
    bekleyen işi fark etmeyebilir ve süreç yavaşlar. Bu risk owner tarafından KABUL EDİLMİŞTİR
    ve pilot-ready çıkış kriteri olarak izlenir.
  reference: docs/product/mvp-scope-v0.1.md#4-pilot-ready-çıkış-kriterleri
```

---

## Kapatılan varsayımlar

```yaml
- id: ASM-0008
  statement: "Auth provider olarak Supabase Auth önerilmektedir (ADR-005)."
  status: validated
  closed_at: 2026-07-14
  resolution: >
    ✅ KAPANDI — Owner kararı: Supabase Auth seçildi. Supabase YALNIZCA authentication
    sağlayıcısıdır. Organization, membership, manager hierarchy, RBAC, authorization ve
    tenant modeli FlowPilot domain'inde ve FlowPilot'ın PostgreSQL'indedir.
    Domain katmanı Supabase SDK'sına bağımlı olamaz; entegrasyon AuthProviderPort
    adapter'ı arkasındadır. LOCK-004 kapandı. Bkz. ADR-005, OQ-001.
  affected_stories: [FP-E01-001, FP-E01-002, FP-E01-003]

- id: ASM-0009
  statement: >
    PRD §7.1'in MVP hedef listesi ile backlog'un kapsamı farklıdır; backlog owner kararını
    takip eder.
  status: validated
  closed_at: 2026-07-14
  resolution: >
    ✅ KAPANDI — Owner kararı: PRD (§7.1, §24 dahil) araştırma ve uzun vadeli ürün vizyonu
    olarak DEĞİŞTİRİLMEDEN korunur. Bağlayıcı teslim kapsamı için ayrı bir doküman
    oluşturuldu: docs/product/mvp-scope-v0.1.md. Bu doküman PRD'nin geniş MVP tanımının
    ÜZERİNDE önceliklidir. PRD'nin mühendislik kuralları (invariant, anti-pattern,
    state machine, güvenlik) tam olarak bağlayıcı kalır. Bkz. OQ-005.
  affected_stories: []

- id: ASM-0005
  statement: >
    "Workflow Runtime Core" (E09) epic'i PRD §47'de listelenmemiştir; ilk dikey dilimin
    çalışabilmesi için türetilmiştir.
  status: validated
  closed_at: 2026-07-14
  resolution: >
    ✅ KAPANDI — Owner'ın gerçek MVP kapsamı "Transactional outbox" ve
    "Idempotent PostgreSQL worker" maddelerini AÇIKÇA içermektedir. Bunlar E09'un
    çekirdeğidir. E09 kapsamdadır ve teyit edilmiştir.
    Bkz. docs/product/mvp-scope-v0.1.md §2.
  affected_stories: [FP-E09-001, FP-E09-002, FP-E09-003, FP-E09-004, FP-E09-005]
```
