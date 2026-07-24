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

- id: ASM-0013
  statement: >
    Production Workflow Runtime Core (Epic E09), definition-version / task / event /
    outbox / inbox sorumluluklarını `workflow_runtime` bounded context'i altında
    GEÇİCİ OLARAK KONSOLİDE eder. domain-boundaries.md §2 bunları workflow_design
    (versions), work_management (tasks), approval ve platform (outbox/inbox) modüllerine
    dağıtır. Çakışmayı önlemek için tüm runtime tabloları 'workflow_runtime_' önekli
    adlandırılmıştır; hiçbiri o modüllerin planlanan tablo adlarını kullanmaz.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    workflow_design / work_management / approval / platform modülleri oluşturulduğunda
    (ilerideki story'ler) sınır uzlaştırması yapılır: runtime, o modüllerin açık
    contract'larını tüketebilir veya ilgili sorumluluk taşınabilir. Tablo öneki
    ayrımı, taşımayı migration işi hâline getirir (refactor değil).
  expires_at: 2026-12-01
  affected_stories: [FP-E09-001, FP-E09-002, FP-E09-003, FP-E09-004, FP-E09-005]
  note: >
    Runtime core'un kendi içinde tutarlı bir "engine" olarak kanıtlanması (spike 12/12)
    ve Purchase Request diliminin çalışabilmesi için bu konsolidasyon owner-onaylı E09
    kapsamıyla uyumludur. ADR-004 §Karar/3 tasarım kararlarına uyar. Bkz. [[ASM-0004]]
    (purchase_request modül yerleşimi — benzer explicit-modül gerekçesi).

- id: ASM-0014
  statement: >
    Workflow runtime dispatcher (worker) PER-TENANT çalışır: her dispatch turu açık bir
    tenant context'i altında yürür ve YALNIZ o tenant'ın vadesi gelmiş outbox/timer
    kayıtlarını RLS altında claim eder. Kuyruk tablolarında queue-geneli bir RLS bypass
    YOKTUR (spike'ın ayrı worker-rolü yaklaşımının aksine, production tek app rolüyle
    daha katı izolasyon seçildi). Hangi tenant'ların işleneceği (çoklu-tenant zamanlama)
    worker'a dışarıdan verilir (--tenant) ve gerçek scheduling ilerideki bir story'dedir.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    Pilot-ready worker operasyonu tasarlanırken: tenant registry contract'ı üzerinden
    aktif tenant enumerasyonu + adil scheduling eklenir. Şu anki per-tenant dispatch
    API'si (run_dispatch_pass(tenant_id)) değişmeden bir scheduler tarafından çağrılır.
  expires_at: 2026-12-01
  affected_stories: [FP-E09-004, FP-E09-005]
  note: >
    Gerekçe: queue-wide görünürlük veren bir RLS policy, sıradan bir app isteğinin de
    tüm tenant'ların outbox payload'ını görmesine kapı açardı. Per-tenant dispatch bunu
    engeller (missing context → deny, ALL tablolar). Maliyet: çoklu-tenant tarama için
    bir üst-katman scheduler gerekir; bu bilinçli olarak ertelendi.

- id: ASM-0015
  statement: >
    Purchase Request kaydı ile workflow instance başlangıcının cross-module
    ATOMİKLİĞİ, composition root'ta (api/wiring.py) kurulan bir COMPOSE UnitOfWork ile
    sağlanır: purchase_request ve workflow_runtime infrastructure adapter'ları TEK
    SQLAlchemy session'ı üzerinde birleşir ve TEK commit/rollback ile yönetilir.
    workflow_runtime, kod kopyalanmadan `WorkflowRuntimeTransactionPort`
    (start_instance_tx / submit_form_tx — commit etmez, sağlanan uow üzerinde çalışır)
    ile katılır. İki bağımsız commit veya distributed transaction YOKTUR.
  impact: medium
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: >
    Approval decision / task inbox story'lerinde tekrar değerlendirilir: aynı compose
    pattern approval kararını da atomik kılacak mı, yoksa event-driven (outbox) bir
    yaklaşım mı tercih edilecek? İkinci modül entegrasyonunda sınır netleşir.
  expires_at: 2026-12-01
  affected_stories: [FP-E06-001, FP-E06-002, FP-E06-003]
  note: >
    Gerekçe: cross-module infrastructure importu YASAK; ama iki modülün adapter'larını
    composition root'ta tek session üzerinde compose etmek dependency-rules'a uygundur
    (wiring yalnız api/deps.py + api/wiring.py'de). PurchaseRequestUnitOfWork port'u
    workflow_runtime'ın WorkflowUnitOfWork'ünü GENİŞLETİR; provider-neutral sınır korunur.
    Bkz. [[ASM-0013]] (runtime boundary konsolidasyonu).

- id: ASM-0016
  statement: >
    MVP onaycı modeli (owner-approved). (a) Tenant başına üç approval role key
    (team_manager, finance, general_manager); her role için tek aktif assignee; aynı
    kullanıcı birden fazla rol taşıyabilir. (b) Organizasyonun rolleri henüz oluşmamışsa,
    ilk onay akışından önce üç rol de AKTİF OWNER'a idempotent atanır (public
    role-management endpoint DEĞİL; tekrar çalıştırmada duplicate üretmez, açık atamaları
    overwrite etmez; aktif owner yoksa kontrollü configuration error). (c) Task
    oluşturulduğunda assignee task'a SABİTLENİR; sonraki rol değişikliği açık task'ları
    etkilemez. (d) Karar yetkisi YALNIZ task'ın assigned_user_id'sine eşit kullanıcıdadır.
    (e) SELF-APPROVAL SERBEST: requester kendi adımını onaylayabilir.
        **SUPERSEDED by ASM-0022 (FP-E06-009, 2026-07-21): self-approval artık YASAKTIR ve
        varsayılan açıktır; (e) maddesi geçersizdir. (a)-(d) yürürlükte kalır.**
  impact: high
  reversible: true
  owner: product
  status: superseded
  validation_method: >
    Owner kararı: tek kullanıcının tüm workflow'u uçtan uca test edebilmesi için MVP'de
    self-approval'a GEÇİCİ olarak izin verilmişti. Bu geçici izin FP-E06-009 ile KALDIRILDI
    (ASM-0022); separation-of-duties artık sabit ve kapatılamaz bir güvenlik kuralıdır.
  expires_at: 2026-12-01
  affected_stories: [FP-E10-001, FP-E10-002, FP-E10-003]
  binding_rule: >
    Self-approval izni gizli feature flag veya hard-code kullanıcı istisnası olarak
    IMPLEMENTE EDİLMEZ — yetki yalnızca assigned_user_id'ye dayanır; requester==approver
    için ÖZEL BİR BLOK YOKTUR. Separation-of-duties pilot-ready sürümde yeniden
    değerlendirilir. Duplicate/eşzamanlı karar koruması (approval_decisions unique +
    version CAS) bu izinden bağımsız olarak her zaman geçerlidir.
  reference: apps/backend/src/flowpilot/modules/approval/README.md

- id: ASM-0017
  statement: >
    Frontend'in yeniden girişte aktif organizasyon context'ini çözebilmesi için
    `GET /v1/me/organizations` eklendi. Bir kullanıcının hangi organizasyonlara üye
    olduğu doğası gereği CROSS-TENANT'tır; organization_memberships üzerindeki tek
    SELECT policy ise tenant-scoped'tur (migration 0001) ve flowpilot_app NOBYPASSRLS
    olduğundan bu listeyi ALAMAZ. Bu nedenle owner onayıyla ADDITIVE migration 0006
    eklendi: kullanıcının YALNIZ KENDİ üyelik satırlarını görebildiği ikinci bir SELECT
    policy (`user_id = current_actor_id`). RLS policy'leri OR ile birleşir; mevcut
    tenant-scope davranışı DEĞİŞMEZ, başka kullanıcının/başka tenant'ın verisi SIZMAZ.
    Aktif org, frontend'de HttpOnly `flowpilot_active_organization` cookie'sinde (yalnız
    org UUID) tutulur; cookie AUTHORIZATION KAYNAĞI DEĞİLDİR — her istekte membership
    backend'de yeniden doğrulanır (stale/uydurma UUID reddedilir).
  impact: medium
  reversible: true
  owner: engineering
  status: validated
  validation_method: >
    Owner onayı (2026-07-19): migration 0006 (actor-scoped membership SELECT policy)
    kabul edildi. Alternatif "migration yok, kapsamı daralt" reddedildi.
  expires_at: 2026-12-01
  affected_stories: [FP-E11-001]
  binding_rule: >
    Cookie tek başına yetki VERMEZ; org context her istekte listMyOrganizations
    (actor-scoped RLS) ile doğrulanır. Bu endpoint bir organization management API'si
    DEĞİLDİR; yalnız actor'ın kendi aktif üyeliklerini döndürür.
  reference: apps/backend/migrations/versions/0006_membership_actor_select_policy.py

- id: ASM-0018
  statement: >
    Davet çekirdeği (FP-E03-001, Dilim A) owner-approved kararları. (a) Davet süresi
    SABİT 7 gündür (`expires_at = created_at + 7 gün`). (b) Davetle YALNIZ `admin` veya
    `member` membership rolü verilebilir; `owner` rolü davet yoluyla VERİLEMEZ (DB CHECK +
    domain reddi). (c) Davet oluşturma/listeleme/iptal YALNIZ aktif `owner` veya `admin`
    üyeye açıktır (merkezi authorization boundary; member ve non-member reddedilir). (d)
    Bu dilim yalnız davet OLUŞTURMA, LİSTELEME ve İPTAL kapsar; davet KABULÜ, üyelik
    oluşturma ve frontend SONRAKİ dilime (Dilim B) aittir — bu dilimde implemente EDİLMEZ.
    (e) Ham davet token'ı kriptografik güvenli üretilir (`secrets`), veritabanında YALNIZ
    SHA-256 hash olarak saklanır, ham değer YALNIZ oluşturma cevabında bir kez döner; audit/
    outbox/log/exception'a YAZILMAZ. (f) E-posta trim+lowercase normalize edilir. (g)
    Üye kaldırma ileride soft-remove olacaktır; kendi talebini onaylama yasağı SABİT bir
    kural olacaktır ve uygun onaycı yoksa blocked/unassigned davranışı uygulanacaktır —
    her ikisi de bu dilimde DEĞİL, sonraki dilimlerde (Dilim C/E) uygulanır.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner kararı (2026-07-20): Dilim A kapsamı ve güvenlik parametreleri onaylandı.
    E-posta gönderimi bu dilimde EKLENMEZ; owner tek kullanımlık davet linkini manuel
    paylaşır (accept_url oluşturma cevabında döner). Ücretli e-posta sağlayıcısı ertelendi.
  expires_at: 2026-12-01
  affected_stories: [FP-E03-001]
  binding_rule: >
    `owner` rolü davetle atanamaz (DB CHECK + domain). Ham token DB'ye YAZILMAZ; yalnız
    SHA-256 hash saklanır. Davet yönetimi (create/list/revoke) owner/admin dışına açılamaz;
    yetki kontrolü merkezi authorization boundary'sindedir, route içinde dağınık rol
    kontrolü YAZILMAZ. Davet kabulü ve üyelik oluşturma bu dilime EKLENMEZ.
  reference: apps/backend/src/flowpilot/modules/organization/domain/invitation.py

- id: ASM-0019
  statement: >
    Davet önizleme + kabul akışı (FP-E03-001, Dilim B) owner-approved kabul semantikleri.
    (a) Kabul YALNIZ authenticated kullanıcı tarafından yapılır; yetki = capability token +
    authenticated actor + e-posta eşleşmesidir (owner/admin permission'ına TABİ DEĞİL).
    (b) Actor'ın `email_snapshot` değeri trim+lowercase normalize edilip davet e-postasıyla
    EŞLEŞMELİDİR; `email_snapshot` NULL ise davet kabul edilemez (403). (c) Davet TEK
    KULLANIMLIKTIR: kabul → `accepted` (accepted_by_user_id + accepted_at + version CAS).
    Aynı actor replay → idempotent `duplicate=true` (yeni membership/audit YOK); farklı actor
    accepted daveti kullanamaz (404, sızdırmaz). (d) Revoked → 404, expired → 410, cross-tenant
    token → 404. (e) Kabul + üyelik oluşturma + audit AYNI transaction'dadır; başarısızlıkta
    yarım üyelik/accepted davet KALMAZ. (f) Kabul yeni kullanıcıya YALNIZ davetteki membership
    rolünü verir; approval role_key ataması YAPMAZ; owner rolü davetle oluşmaz. (g) Kullanıcı
    davet sonrası başka yolla AKTİF üye olmuşsa: mevcut rol DEĞİŞTİRİLMEZ/yükseltilmez, yeni
    membership oluşturulmaz, davet accepted olarak kapatılır, `duplicate=true` + mevcut rol
    döner. Suspended/removed üyelik OTOMATİK reaktive edilmez → conflict (409). (h) Frontend
    kabul sayfası ve e-posta gönderimi bu dilimde YOK (sonraki dilim / ertelenmiş). (i)
    Idempotency-Key OPSİYONELDİR: yoksa tek-kullanımlık davet state'i doğal idempotency
    anchor'ıdır; varsa aynı actor + org + aynı payload replay → önceki sonuç (`duplicate=true`,
    yeni membership/audit YOK), aynı key farklı payload/org → **409** (hiçbir state değişmeden).
    Idempotency, `organization_invitation_accept_idempotency` (migration 0008) ile davet
    OLUŞTURMA idempotency'sinden AYRI tutulur; ham token/token_hash saklanmaz.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner kararı (2026-07-20): Dilim B kapsamı, kabul güvenlik kuralları ve accept
    Idempotency-Key sözleşmesi onaylandı. Kabul idempotency'si için additive migration 0008
    yazıldı (0007 immutable; create idempotency alanları yeniden kullanılmadı).
  expires_at: 2026-12-01
  affected_stories: [FP-E03-001]
  binding_rule: >
    E-posta eşleşmesi zorunludur; email_snapshot yoksa kabul reddedilir. Davet tek
    kullanımlıktır ve tek actor'a pinlenir. Mevcut aktif üyeliğin rolü kabulle değiştirilmez.
    Suspended/removed üyelik otomatik aktifleştirilmez. Owner rolü hiçbir kabul yolundan
    oluşmaz. Ham token log/audit/outbox/exception mesajına ve idempotency alanlarına YAZILMAZ.
    Idempotency-Key: same-key/same-payload replay → aynı sonuç (`duplicate=true`); same-key/
    different-payload veya different-org → 409; header yoksa davet state doğal anchor'dır.
    accept idempotency kaydı create idempotency'siyle karıştırılmaz (ayrı tablo).
  reference: apps/backend/src/flowpilot/modules/organization/application/invitation_accept.py

- id: ASM-0020
  statement: >
    Üye yönetimi (FP-E03-002, Dilim C) owner-approved yönetim semantikleri. (a) Bu dilim
    YALNIZ `organization_memberships.role` (owner/admin/member governance rolü) ve `status`
    yönetir; workflow approval rolleri (`team_manager`/`finance`/`general_manager`
    = `approval_role_assignments.role_key`) AYRIDIR ve bu dilimde DEĞİŞTİRİLMEZ. (b) Yetki
    iki katmanlıdır: merkezi coarse permission katalogu (`organization.member.read/role.change/
    suspend/reactivate/remove`) + hedefe göre ince domain policy. Route içinde dağınık
    `role == "owner"` kontrolü YAZILMAZ. (c) `owner`: kendisi HARİÇ tüm üyeleri yönetir, owner'a
    yükseltebilir, başka bir owner'ı düşürebilir (son-owner invariant'ı korunmak şartıyla).
    `admin`: YALNIZ `member` hedefleri yönetir, member→admin yapabilir, owner VEREMEZ,
    owner/admin hedeflere DOKUNAMAZ (403). `member`: 403. Non-member: 404 (varlık sızdırmaz).
    (d) Kullanıcı kendi rol/status/üyeliğini DEĞİŞTİREMEZ → 409. (e) Status geçişleri:
    active↔suspended, active/suspended→removed. `removed` TERMİNALDİR (reaktive YOK, rol
    değişimi YOK). Fiziksel DELETE YOK (soft-remove; app rolünden DELETE grant KALDIRILDI,
    migration 0009). No-op (aynı değere set) idempotenttir → `duplicate=true`, yeni yazım/audit
    YOK. (f) Son aktif owner invariant'ı: her tenant'ta DAİMA ≥1 aktif owner kalır; owner'ı
    deaktive eden değişiklik aktif owner satırlarını `FOR UPDATE` ile kilitler ve tenant-scoped
    transaction advisory lock ile serileştirir → eşzamanlı iki demotion sıfır owner bırakamaz
    (mutual-demotion deadlock'u da bu serileştirmeyle önlenir). (g) `suspend`/`remove`, hedefin
    AKTİF onay sorumluluğu (aktif `approval_role_assignment` VEYA pending/active workflow
    approval task) varsa 409 ile ENGELLENİR; cross-module kontrol organization domain'inin
    approval/workflow infrastructure'ını DOĞRUDAN import etmesiyle DEĞİL, composition root'ta
    wire edilen application READ contract'ı (`ApprovalResponsibilityQuery`) ile yapılır. (h)
    Değişiklik + version bump + audit AYNI transaction'dadır; optimistic CAS (`version`)
    stale write → 409; audit başarısızlığı tüm işlemi rollback eder; stale/no-op yolunda audit
    YAZILMAZ. Listeleme `provider_subject`/`auth_provider`/JWT DÖNMEZ (yalnız email_snapshot,
    null olabilir); `removed` üyeler durumlarıyla listede KALIR. (i) Frontend bu dilimde YOK
    (sonraki dilim). E-posta gönderimi ve Supabase ayar değişikliği YOK.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner kararı (2026-07-21): Dilim C kapsamı, iki katmanlı yetki modeli, son-owner
    invariant'ı, soft-remove terminal semantiği ve approval-sorumluluk guard'ı onaylandı.
    Governance rolü (membership.role) ile approval rolü (role_key) ayrımı korunur. Additive
    migration 0009 yazıldı (0001–0008 immutable): `version`/`updated_at` kolonları + backfill,
    tenant-scoped UPDATE RLS policy, DELETE grant REVOKE, tenant-scoped index'ler.
  expires_at: 2026-12-01
  affected_stories: [FP-E03-002]
  binding_rule: >
    Bu dilim yalnız membership.role/status yönetir; approval role_key ataması yapılmaz. Yetki
    merkezi authorization boundary + hedef domain policy'sindedir (route'ta dağınık rol kontrolü
    yasak). admin yalnız member hedefleri yönetir ve owner veremez; owner kendisi hariç herkesi
    yönetir. Kullanıcı kendini değiştiremez (409). removed terminaldir; fiziksel DELETE yok
    (app rolünde DELETE grant yok). Her tenant'ta ≥1 aktif owner kalır (FOR UPDATE + advisory
    lock). Aktif onay sorumluluğu olan kullanıcı suspend/remove edilemez (409, cross-module READ
    contract ile). Değişiklik + audit tek transaction; optimistic CAS ile stale → 409; no-op →
    duplicate (audit yok). Listeleme identity/JWT sızdırmaz.
  reference: apps/backend/src/flowpilot/modules/organization/application/member_handlers.py

- id: ASM-0021
  statement: >
    Gerçek kullanıcılara onay rolü atama (FP-E10-004, Dilim) owner-approved semantikleri.
    (a) Governance rolleri (owner/admin/member = organization_memberships.role) ile workflow
    approval rolleri (team_manager/finance/general_manager = approval_role_assignments.role_key)
    AYRIDIR ve BİRLEŞTİRİLMEZ; bir kullanıcı governance'ta member iken approval'da finance
    olabilir ve aynı kullanıcı birden fazla approval role taşıyabilir. (b) owner/admin approval
    rollerini listeler ve değiştirir (merkezi permission: approval.role_assignment.read/change);
    member 403; non-member/cross-tenant 404 (varlık sızdırmaz). Route'ta dağınık rol kontrolü
    YOK. (c) Bir approval role YALNIZ aynı organizasyonda AKTİF üyeliği olan bir kullanıcıya
    atanabilir; suspended/removed üye, başka tenant üyesi veya bulunmayan kullanıcı atanamaz
    (aktif değil → 409, üye değil → 404). Bu dilimde kullanıcının kendine approval role vermesi
    YASAK DEĞİLDİR (self-approval engeli SONRAKİ dilim). (d) Atama değişikliği tarihçe koruyan
    modeldir: eski aktif atama `revoked` yapılır (version+1, updated_at), yeni aktif atama satırı
    (yeni version) eklenir; fiziksel DELETE YOK (app rolünde DELETE grant yok, migration 0010).
    Aynı tenant+role_key için DAİMA tek aktif atama (partial unique). No-op (aynı kullanıcı) →
    duplicate=true, yeni atama/version/audit YOK. (e) version optimistic CAS: role_key başına
    aktif atamada MONOTONİK ilerler; mevcut aktif atama varsa expected_version zorunludur (yoksa
    422) ve eşleşmezse 409; aktif atama yoksa create (expected_version opsiyonel). Tenant+role
    advisory xact lock + FOR UPDATE + partial unique ile eşzamanlı iki farklı-user atamada YALNIZ
    biri kazanır, diğeri 409 (çift aktif atama/çift audit oluşmaz). (f) Değişiklik + version +
    audit AYNI transaction (`approval.role_assignment.changed`; metadata: role_key, previous/new
    assignment_id + user_id, actor, previous/new version — token/JWT/hassas identity YOK); audit
    başarısızlığı rollback; no-op/stale audit YAZMAZ. (g) MEVCUT workflow task pinning DEĞİŞMEZ:
    task oluşturulduğu anki assignee'ye pinlenir (assigned_user_id snapshot); reassignment mevcut
    active/pending task'ları veya geçmiş karar kayıtlarını DEĞİŞTİRMEZ — yalnız SONRAKİ satın alma
    talepleri yeni atamayı kullanır. Açık task'ların toplu yeniden atanması kapsam DIŞI. Inbox
    yalnız pinlenmiş assigned_user_id'ye görev gösterir. (h) EnsureDefaultApprovalRoleAssignments
    güvenli varsayılan olarak kalır: eksik/ilk kurulumda owner seed eder ama MEVCUT aktif atamayı
    EZMEZ (ON CONFLICT DO NOTHING); reassignment sonrası yeni talepler yeni kullanıcıyı kullanır.
    (i) Listeleme provider_subject/auth_provider/JWT DÖNMEZ (yalnız email_snapshot, null olabilir),
    deterministik sırada (team_manager → finance → general_manager). (j) Frontend approval-role
    yönetimi ve self-approval engeli bu dilimde YOK (sonraki dilim/ler).
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner kararı (2026-07-21): Dilim kapsamı, governance/approval rol ayrımı, aktif-üye atama
    kuralı, tarihçe koruyan reassignment, optimistic concurrency ve task pinning snapshot davranışı
    onaylandı. Additive migration 0010 yazıldı (0001–0009 immutable): version kolonu + backfill,
    tenant-scoped index'ler, DELETE grant REVOKE; mevcut FOR-ALL RLS policy UPDATE'i kapsar ve
    partial unique active constraint korunur.
  expires_at: 2026-12-01
  affected_stories: [FP-E10-004]
  binding_rule: >
    Governance rolü ile approval role_key ayrı tutulur; bir kullanıcı birden fazla approval role
    taşıyabilir. owner/admin approval rol atar (merkezi permission; route'ta dağınık rol kontrolü
    yasak); yalnız aktif üye atanabilir (suspended/removed/non-member/cross-tenant reddedilir).
    Reassignment eski atamayı revoked yapar + yeni aktif atama ekler (fiziksel DELETE yok; tek
    aktif atama partial unique ile). version optimistic CAS + tenant+role advisory lock: eşzamanlı
    atamada tek kazanan, diğeri 409; no-op → duplicate (audit yok). Mevcut workflow task'lar
    pinlenmiş assignee'de kalır; yalnız sonraki talepler yeni atamayı kullanır. Owner seed mevcut
    gerçek atamayı ezmez. Self-approval engeli ve frontend sonraki dilimdedir.
  reference: apps/backend/src/flowpilot/modules/approval/application/role_assignment_handlers.py

- id: ASM-0006
  statement: >
    Dosya eki için S3-compatible storage portu MVP'de MinIO (local development) üzerinde
    doğrulanır; production S3-compatible sağlayıcı kararı ERTELENMİŞTİR. Hosting kararı
    verildi (ADR-010 — Render Frankfurt; LOCK-006 kapandı) ancak object storage MVP'de aktif
    kullanılmadığından ayrı bir sağlayıcı bu aşamada seçilmemiştir; dosya eki akışı pilota
    girerse seçilecektir.
  impact: low
  reversible: true
  owner: engineering
  status: unvalidated
  validation_method: "Dosya eki akışı pilota girdiğinde S3-compatible sağlayıcı seçilir (ADR-010'da ertelendi)."
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

- id: ASM-0022
  statement: >
    Kendi talebini onaylamayı engelleme + uygun onaycı bekleme (FP-E06-009) owner-approved
    kuralları — ASM-0016(e)'yi SÜPERSE eder. (a) Self-approval BÜTÜN tenant'larda YASAKTIR,
    SABİTTİR ve VARSAYILAN AÇIKTIR: organizasyon ayarı veya kapatma seçeneği YOKTUR. Talep
    sahibi (request_created_by / workflow instance context'teki requester_id) kendi talebindeki
    HİÇBİR onay adımını sonuçlandıramaz; başka governance/approval rolü taşısa ya da ilgili
    role_key'e atanmış olsa bile. (b) Atama davranışı: bir adımın oluşturma-anındaki çözülen
    assignee'si talep sahibiyse görev talep sahibine ATANMAZ (assigned_user_id null kalır),
    approver_role korunur ve adım sırası kendisine geldiğinde `blocked` (NON-terminal) olur;
    `blocked_reason = self_approval_no_eligible_assignee`, talep sahibinin inbox'ında GÖRÜNMEZ.
    Sonraki bir adım talep sahibine çözülüyorsa önceki adımlar normal ilerler, sıra o adıma
    gelince workflow blocked olur ve DAHA İLERİ İLERLEMEZ; önceki tamamlanmış görevler
    değişmez. Sessiz owner/requester fallback YOKTUR. (c) Karar anı savunması (defense-in-depth):
    assignee snapshot'ı yanlışlıkla requester olsa (legacy/veri uyumsuzluğu) veya doğrudan API
    çağrısı yapılsa bile decision path reddedilir — task state/decision/workflow DEĞİŞMEZ,
    HTTP 409 döner ve güvenlik denial audit'i (`approval.self_approval_blocked`) yazılır; blocked
    task approve/reject EDİLEMEZ. (d) Dar kapsamlı çözümleme: yalnız self-approval nedeniyle
    blocked kalan MEVCUT adım için `resolve-assignment` endpoint'i vardır (GENEL açık-task
    reassignment DEĞİL). Aday keyfi user_id DEĞİL, o rolün MEVCUT aktif approval_role_assignment'ı
    kaynak alınır; aday aynı organizasyonda aktif üye olmalı ve talep sahibi OLMAMALIDIR; uygun
    aday yoksa 409 ve state değişmez; başarılıysa blocked→active, assigned_user_id yeni kullanıcı,
    blocked_reason temizlenir, version+1, audit (`approval.task_assignment_resolved`). Normal
    active/pending task'lar TOPLU yeniden atanmaz; snapshot/pinning invariant'ı korunur. (e)
    Görünürlük: owner/admin blocked task'ları listeler (`approval.blocked_task.read`) ve çözer
    (`approval.blocked_task.resolve`); member 403, non-member/cross-tenant 404. Blocked durumu API
    ve audit üzerinden açıkça görünür; instance running/waiting, purchase request in_approval
    kalır (yeni instance/PR status EKLENMEDİ). (f) Eşzamanlılık: iki resolve yarışında task satırı
    FOR UPDATE + version CAS ile tek kazanır; role-change ile resolve yarışında aday hep aktif üye
    + non-requester; requester karar ile resolve yarışında requester ASLA kazanamaz, workflow bir
    kez ilerler, çift audit/decision oluşmaz. (g) Bloklama/çözümleme/ret olayları audit'te görünür
    (`approval.task_blocked` / `approval.task_assignment_resolved` / `approval.self_approval_blocked`);
    JWT/token/hassas identity audit'e YAZILMAZ; no-op/başarısız resolve yeni başarılı-state audit'i
    üretmez. (h) Frontend blocked-task yönetimi SONRAKİ dilimdedir.
  impact: high
  reversible: false
  owner: product
  status: validated
  supersedes: [ASM-0016]
  validation_method: >
    Owner kararı (2026-07-21): self-approval kalıcı olarak yasaklandı ve varsayılan açık,
    kapatılamaz güvenlik kuralı oldu. Uygun onaycı yoksa görev blocked olur; sessiz fallback yok.
    Additive migration 0011 (0001–0010 immutable): workflow_runtime_tasks status CHECK'e `blocked`,
    `blocked_reason`/`blocked_at` nullable kolonları + reason CHECK, (tenant_id, status) index.
    Instance/PR status'una yeni değer eklenmedi (blocked task-seviyesinde temsil edilir).
  expires_at: 2026-12-01
  affected_stories: [FP-E06-009]
  binding_rule: >
    Self-approval bütün tenant'larda yasaktır, kapatılamaz ve varsayılan açıktır (gizli flag /
    istisna YOK). Uygun onaycı yoksa görev talep sahibine verilmez; blocked olur ve inbox'ta
    görünmez. Karar anı savunması requester'ı her koşulda reddeder (409 + security audit; state
    değişmez). Yalnız self-approval nedeniyle blocked kalan adım, mevcut aktif role assignment'tan
    alınan uygun (aktif üye, non-requester) kullanıcıya resolve edilir; normal açık task'lar toplu
    yeniden atanmaz ve pinning invariant'ı korunur. blocked task approve/reject edilemez; fiziksel
    DELETE yok. Owner/admin blocked görür ve çözer (merkezi permission; route'ta dağınık rol
    kontrolü yok). Self-approval prevention frontend'i sonraki dilimdedir.
  reference: apps/backend/src/flowpilot/modules/workflow_runtime/application/service.py

- id: ASM-0023
  statement: >
    Organizasyon davet yönetimi ve güvenli davet kabul arayüzü (FP-FE-001, frontend dilim)
    güvenlik ve kapsam kararları. Backend/migration/alembic head (0011) DEĞİŞMEDİ; frontend
    yalnız mevcut davet/önizleme/kabul sözleşmelerini tüketir. (a) Ham davet token'ı bir
    CAPABILITY'dir ve YALNIZ iki güvenli taşıyıcıda bulunur: (1) create sonucunda bir kez
    gösterilen davet URL'sinin query parametresi, (2) kabul akışında server tarafında şifreli
    bound server-action argümanı. Token console.log'a, analytics event'ine, tarayıcı storage'ına
    (localStorage/sessionStorage/cookie), error boundary mesajına, React Query/devtools key'ine,
    DOM data-attribute'una, davet listesi response'una veya ham API debug çıktısına ASLA yazılmaz.
    (b) Davet URL'si create başarı modalında YALNIZ BİR KEZ gösterilir; modal kapanınca istemci
    state'inden düşer ve yeniden gösterilmez; idempotent replay (duplicate=true, token=null)
    bağlantıyı yeniden ÜRETMEZ, güvenli bilgi mesajı gösterir. (c) Idempotency-Key mantıksal işlem
    başına İSTEMCİDE üretilir (kısa ömürlü React ref; storage/URL/log DEĞİL) ve AYNI mantıksal
    işlemin retry'ında AYNI kalır — böylece kaybolan cevap/çift submit backend'de tek işlem olur.
    Create için mantıksal işlem = (e-posta + rol) fingerprint'i: aynı payload retry → aynı key
    (React'in hata sonrası uncontrolled alanları sıfırlamasına rağmen, key her submit'te onClick ile
    gizli input'a yeniden yazılır), payload değişince → yeni key, başarı modalı kapanınca temizlenir.
    Accept için mantıksal işlem = davet (org+token; mount başına sabit): retry aynı key, başarıdan
    sonra temizlenir, farklı davet (yeni mount) → yeni key. Server tarafı gelen key'i UUID olarak
    doğrular; eksik/biçimsiz ise güvenli fallback olarak üretir (her istekte daima geçerli key gider).
    Key hassas değildir (rastgele UUID, token DEĞİL); yalnız transport için gizli input'a yazılır,
    browser storage/cookie/URL/console/analytics/hata mesajına yazılmaz. (d) Public önizleme
    (`GET /v1/invitations/preview`) auth'suz çağrılır ve YALNIZ güvenli alanları gösterir
    (organizasyon adı, rol, son geçerlilik, durum); davet edilen e-posta, provider_subject,
    auth_provider veya JWT GÖSTERİLMEZ. E-posta uyuşmazlığında gerçek davetli e-postası ifşa
    edilmez; sabit "Bu davet farklı bir e-posta adresi için oluşturulmuş." mesajı gösterilir.
    (e) Kabul için giriş gereken kullanıcı login'e yönlendirilirken dönüş yolu YALNIZ uygulama-içi
    RELATİF URL olarak (open-redirect guard: `//`, `/\`, mutlak URL reddedilir) taşınır; token
    login akışında storage'a değil, yalnız URL query'sinde kalır. Başarılı kabulden sonra org/token
    query'si `history.replaceState` ile en erken güvenli anda URL'den temizlenir (başarı ekranı
    görünmeye devam eder; refresh güvenli). (f) Frontend rol/görünürlük (Ayarlar → Ekip → Davetler
    menüsü ve owner/admin gate) YALNIZ UX içindir; backend authorization tek kaynaktır. member
    davet ekranında güvenli "yetkiniz yok" görür (403), non-member/cross-tenant sızıntı olmaz (404).
    Davet oluşturmada rol yalnız admin|member seçilebilir (owner SUNULMAZ). (g) HTTP eşlemesi
    kullanıcıya güvenli: 401 → giriş, 403 → yetkisiz/e-posta uyuşmazlığı, 404 → geçersiz davet,
    409 → çakışma (idempotent tekrar güvenli), 410 → süresi dolmuş, 422 → doğrulama, 5xx/ağ → tekrar
    dene; backend teknik detayı (stack, FastAPI 422 dizisi) kullanıcıya taşınmaz. (h) E-posta teslimi
    KAPSAM DIŞIDIR (bağlantı elle paylaşılır); üye yönetimi, approval-role yönetimi ve blocked-task
    yönetimi frontend'i bu dilimde YOK (sonraki dilim/ler). Yeni state-yönetimi/UI kütüphanesi
    eklenmedi; mevcut tasarım dili korundu.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner talimatı (2026-07-23): davet yönetimi + güvenli kabul frontend'i, token'ın URL + kısa
    ömürlü istemci state dışında hiçbir yerde tutulmaması, tek seferlik bağlantı gösterimi, relatif
    dönüş URL'si, önizlemede e-posta gizliliği ve frontend authz'ın UX-only olması onaylandı.
    Takip (2026-07-24, owner talimatı): Idempotency-Key yaşam döngüsü incelendi ve düzeltildi —
    key artık istemcide mantıksal işlem başına üretilip retry'da korunuyor (önceden her server-action
    çağrısında yeniden üretiliyordu), başarıdan sonra temizleniyor; storage/URL/log'a yazılmıyor.
    Backend/migration DEĞİŞMEDİ; alembic head 0011; release_verify tüm kapılar yeşil.
  expires_at: 2026-12-01
  affected_stories: [FP-FE-001]
  binding_rule: >
    Ham davet token'ı yalnız davet URL'sinde (bir kez gösterilir) ve server-side şifreli bound
    argümanda bulunur; log/analytics/browser storage/error mesajı/query-cache key/DOM
    data-attribute/liste response'una ASLA yazılmaz. Idempotency-Key mantıksal işlem başına
    istemcide üretilir ve retry'da AYNI kalır (create: e-posta+rol fingerprint; accept: davet/mount
    sabit); başarıdan sonra temizlenir; storage/URL/log'a yazılmaz; server key'i UUID doğrular ve
    eksik/biçimsizse güvenli fallback üretir.
    Public önizleme yalnız güvenli alanları döner (e-posta/provider_subject/auth_provider/JWT
    gösterilmez); e-posta uyuşmazlığında gerçek e-posta ifşa edilmez. Login dönüş yolu yalnız
    relatif uygulama-içi URL (open-redirect guard); başarılı kabulde token URL'den temizlenir.
    Frontend görünürlük UX-only, backend authorization tek kaynak (member 403, cross-tenant 404).
    E-posta teslimi ve diğer yönetim ekranları kapsam dışıdır.
  reference: apps/web/src/features/invitations/actions.ts

- id: ASM-0024
  statement: >
    Organizasyon üye yönetimi arayüzü (FP-FE-002, frontend dilim) güvenlik ve kapsam kararları.
    Backend/migration/alembic head (0011) DEĞİŞMEDİ; frontend yalnız mevcut sözleşmeleri tüketir:
    GET /v1/organizations/{id}/members ve PATCH .../members/{user_id} (body: role?/status?/
    expected_version → response: membership_id/user_id/role/status/version/duplicate). (a) Frontend
    rol/görünürlük (Ayarlar → Ekip → Üyeler menüsü, owner/admin gate, satır-bazlı aksiyon
    görünürlüğü) YALNIZ UX içindir; backend authorization TEK karar kaynağıdır ve frontend bunu
    bypass etmeye çalışmaz. member kullanıcı ekranı kullanamaz (403 güvenli mesaj), non-member/
    cross-tenant kaynak sızdırmadan 404 gösterilir. (b) Owner kendisi dışındaki herkesi yönetir
    (owner/admin/member rol; son-owner değilse owner düşürme; suspend/reactivate/remove). Admin
    YALNIZ member hedefleri yönetir, member'ı admin yapabilir, owner rolü VEREMEZ, owner/admin
    hedefte işlem yapamaz. Self satırda hiçbir mutasyon aksiyonu sunulmaz (açıklamalı); self tespiti
    frontend'de e-posta eşleşmesiyle yapılır (best-effort UX — backend `/me` FlowPilot user_id
    döndürmüyor; gerçek self-mutation engeli backend'de 409). (c) Removed üyelik TERMİNAL gösterilir:
    satır listede kalır ama rol/durum aksiyonu sunulmaz; reactivate removed'da gösterilmez.
    (d) Mutasyonlar optimistic concurrency (expected_version, güncel satırdan) ile yapılır. 409
    stale conflict OTOMATİK ve körlemesine retry EDİLMEZ: liste yeniden fetch edilir (revalidatePath),
    açık modalda resubmit engellenir, kullanıcı güncel version'ı görüp kararı tekrar verir. (e) Backend
    TÜM iş çakışmalarını 409 + ham Türkçe domain detay'ı ile döndürür; ham detay KULLANICIYA
    GÖSTERİLMEZ. Frontend ham detay'ı ayırt edici kararlı belirteçlerle güvenli sabit mesajlara eşler
    (stale / self / son-owner / onay-sorumluluğu / removed / geçersiz-geçiş); sınıflandırılamayan 409
    güvenli genel çakışma mesajı alır. Bu, backend contract'ının makine-okunur 409 kodu içermemesine
    karşı bilinçli frontend adaptasyonudur (backend workaround DEĞİL). (f) No-op mutasyon (duplicate=
    true) güvenli "değişiklik yapılmadı" mesajıyla gösterilir; kullanıcının seçemeyeceği roller
    dropdown'da hiç sunulmaz (owner admin'e owner seçeneği görünmez), no-op rol submit'i engellenir.
    (g) Güvenlik: provider_subject/auth_provider/JWT frontend tiplerine/DOM'a alınmaz; ham backend
    response console.log/analytics/error mesajına basılmaz; üye listesi ve target user_id browser
    storage'a yazılmaz (yalnız request transport). (h) Approval-role yönetimi, blocked-task yönetimi
    ve e-posta teslimi bu dilimde YOK (sonraki frontend dilimleri). Yeni state-yönetimi/UI kütüphanesi
    eklenmedi; mevcut tasarım dili korundu.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner talimatı (2026-07-24): üye yönetimi frontend'i (listeleme, rol değiştirme, suspend/
    reactivate/remove), expected_version optimistic concurrency, stale conflict'in otomatik retry
    edilmemesi, removed terminal gösterimi, self-mutation aksiyonlarının sunulmaması, son-owner ve
    onay-sorumluluğu çakışmalarının güvenli mesajlarla gösterilmesi ve frontend authz'ın UX-only
    olması onaylandı. Backend/migration DEĞİŞMEDİ; alembic head 0011; release_verify tüm kapılar yeşil.
  expires_at: 2026-12-01
  affected_stories: [FP-FE-002]
  binding_rule: >
    Üye yönetimi frontend görünürlüğü UX-only'dir; backend authorization tek karar kaynağıdır
    (member 403, cross-tenant 404, self/son-owner/onay-sorumluluğu backend'de 409). Mutasyonlar
    expected_version ile yapılır; stale 409 otomatik retry edilmez (liste tazelenir, kullanıcı
    yeniden karar verir). Backend 409 ham detay'ı kullanıcıya gösterilmez; güvenli sabit mesajlara
    sınıflandırılır (bilinmeyen → genel çakışma). Removed üyelik terminaldir (aksiyon yok). Hassas
    identity (provider_subject/auth_provider/JWT) gösterilmez/loglanmaz; üye listesi ve target
    user_id browser storage'a yazılmaz. Approval-role/blocked-task/e-posta teslimi kapsam dışıdır.
  reference: apps/web/src/features/members/actions.ts

- id: ASM-0025
  statement: >
    Onay rolü yönetimi arayüzü (FP-FE-003, frontend dilim) güvenlik ve kapsam kararları.
    Backend/migration/alembic head (0011) DEĞİŞMEDİ; frontend yalnız mevcut sözleşmeleri tüketir:
    GET /v1/organizations/{id}/approval-roles (aktif atamalar: assignment_id/role_key/
    assigned_user_id/assigned_user_email/status/version/created_at/updated_at) ve PUT
    .../approval-roles/{role_key} (body: user_id + expected_version?; response: +duplicate).
    (a) Approval role_key seti workflow onay sorumluluklarıdır (team_manager → Takım Yöneticisi,
    finance → Finans Sorumlusu, general_manager → Genel Müdür) ve org-yönetişim rolünden
    (owner/admin/member) AYRIDIR. Sabit 3 rol için kart gösterilir; her kartta mevcut atanan
    kullanıcı veya "atanmadı". (b) Görünürlük UX-only; backend policy TEK karar kaynağıdır
    (APPROVAL_ROLE_ASSIGNMENT_READ/CHANGE → owner VE admin; member 403; non-member/cross-tenant
    404). Sayfa owner/admin gate'lidir (member güvenli 403 ekranı görür). (c) Adaylar YALNIZ AKTİF
    üyelerdir (suspended/removed atanamaz — backend 409). Bir kullanıcı birden fazla onay rolü
    taşıyabilir (backend destekler) → frontend başka rol taşıyor diye adayı ELEMEZ. Self-assignment
    bu dilimde YASAK DEĞİLDİR (self-approval engeli karar anında blocked-task ile ayrı dilimdedir).
    (d) Atama PUT ile rol-bazlıdır (toplu değil). Optimistic concurrency: mevcut aktif atama varsa
    expected_version gönderilir; ilk atamada gönderilmez (backend'in expected_version-required 422'si
    frontend'de stale-refresh olarak sınıflandırılır). Stale 409 OTOMATİK retry EDİLMEZ: liste
    revalidatePath ile yenilenir, açık modalda resubmit engellenir, kullanıcı güncel version ile
    yeniden karar verir. (e) No-op (mevcut kullanıcıyı tekrar seçmek) submit edilemez; seçim
    yapılmadan submit edilemez; duplicate=true güvenli "zaten atanmış" mesajıyla gösterilir.
    (f) Backend 409/422 ham detay'ı KULLANICIYA GÖSTERİLMEZ; kararlı belirteçlerle güvenli sabit
    mesajlara sınıflandırılır (stale / geçersiz-üye-durumu / geçersiz-rol / genel). (g) Task pinning:
    atama değişikliği MEVCUT açık onay görevlerini DEĞİŞTİRMEZ; yalnız yeni oluşturulacak görevler
    yeni atamayı kullanır (backend garantisi). UI mevcut görevleri "yeniden atandı" gibi göstermez ve
    toplu görev taşıma iddiasında bulunmaz. (h) Backend REMOVE/DELETE endpoint'i YOKTUR → kaldır
    butonu oluşturulmadı. (i) Güvenlik: provider_subject/auth_provider/JWT frontend tiplerine/DOM'a
    alınmaz; ham backend response console.log/analytics/error mesajına basılmaz; atama/üye listesi ve
    target user_id browser storage'a yazılmaz. (j) Bu dilim yalnız approval-role configuration UI'dır;
    blocked-task resolve UI sonraki frontend dilimidir; üye suspend/remove FP-FE-002 içindedir;
    e-posta teslimi ve hosting kapsam dışıdır. Yeni state-yönetimi/UI kütüphanesi eklenmedi.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Owner talimatı (2026-07-24): onay rolü yönetimi frontend'i (3 sabit rol kartı, aktif-üye
    adayları, rol-bazlı PUT atama, optimistic concurrency, stale'in otomatik retry edilmemesi,
    no-op engeli, task pinning gösterimi, remove endpoint'i olmadığı için kaldır butonu olmaması)
    ve frontend authz'ın UX-only olması onaylandı. Backend/migration DEĞİŞMEDİ; alembic head 0011;
    release_verify tüm kapılar yeşil.
  expires_at: 2026-12-01
  affected_stories: [FP-FE-003]
  binding_rule: >
    Onay rolü yönetimi frontend görünürlüğü UX-only'dir; backend policy tek karar kaynağıdır
    (owner/admin yönetir, member 403, cross-tenant 404). Adaylar yalnız aktif üyelerdir; bir
    kullanıcı birden fazla onay rolü taşıyabilir. Atama rol-bazlı PUT + optimistic expected_version
    (ilk atamada omit) ile yapılır; stale 409 otomatik retry edilmez. No-op/duplicate güvenli
    gösterilir. Backend 409/422 ham detay'ı gösterilmez; güvenli sabit mesajlara sınıflandırılır.
    Mevcut açık görevler pinlenir (yeniden atanmaz); yalnız yeni görevler yeni atamayı kullanır.
    Remove endpoint'i olmadığı için kaldır butonu yoktur. Hassas identity gösterilmez/loglanmaz;
    atama/üye verisi ve target user_id browser storage'a yazılmaz. Blocked-task resolve UI, üye
    yönetimi, e-posta teslimi ve hosting kapsam dışıdır.
  reference: apps/web/src/features/approval-roles/actions.ts

- id: ASM-0026
  statement: >
    Engellenen onay görevleri arayüzü (FP-FE-004, frontend dilim) güvenlik, kapsam ve sözleşme
    kararları. Backend/migration/alembic head (0011) DEĞİŞMEDİ; frontend yalnız mevcut sözleşmeleri
    tüketir: GET /v1/organizations/{id}/approval-tasks/blocked (task_id/purchase_request_id?/
    approver_role/status/blocked_reason?/requester_user_id?/version/created_at/updated_at) ve POST
    .../approval-tasks/{task_id}/resolve-assignment. (a) KRİTİK SÖZLEŞME: resolve endpoint'i KULLANICI
    SEÇİMİ ALMAZ — request body/user_id/expected_version/Idempotency-Key YOK; yalnız task_id path'ten
    gelir. Backend adayı KENDİSİ mevcut aktif approval-role assignment'tan (task.approver_role için)
    seçer; "keyfi user_id ALINMAZ". Bu nedenle istenen aday-SEÇİM modalı (owner talebindeki UI)
    backend ile uyumsuzdu; owner kararıyla (2026-07-24) sözleşme-sadık SEÇİMSİZ onay akışı uygulandı:
    blocked görev listesi + tek "Atamayı çöz" onay diyaloğu. Aday-seçim UI, aday-listeleme endpoint'i
    ve frontend aday-türetme YAPILMADI (backend workaround'dan kaçınıldı). (b) Görünürlük UX-only;
    backend policy TEK karar kaynağıdır (APPROVAL_BLOCKED_TASK_READ/RESOLVE → owner/admin; member 403;
    non-member/cross-tenant 404). Sayfa owner/admin gate'lidir. (c) blocked_reason backend'de CHECK ile
    kısıtlı; tek gerçek değer `self_approval_no_eligible_assignee` → "Kendi talebini onaylama engeli".
    Bilinmeyen/null reason güvenli genel fallback ("Atama sorunu") alır; ham reason kullanıcıya
    gösterilmek zorunda değildir ve DOM'a dump edilmez. (d) Resolve yaşam döngüsü (backend): blocked →
    çözülür, aday task'a pinlenir, requester≠aday runtime'da zorlanır (self-approval), YALNIZ seçili
    görevi etkiler, global approval-role assignment DEĞİŞMEZ, audit yazılır. UI bunu doğru yansıtır:
    "yalnız bu görevi etkiler; onay rolü yapılandırmasını değiştirmez"; approve/reject sunmaz; workflow
    step'i otomatik tamamlanmış göstermez. (e) Backend concurrency'yi kendi içinde yönetir; frontend
    version GÖNDERMEZ (sahte version üretilmez). Her 409 çakışmasında liste revalidatePath ile
    tazelenir (otomatik retry YOK); modalda resubmit engellenir (stale/not-blocked/candidate-inactive/
    generic → yalnız Kapat), no_assignment ise rol atandıktan sonra tekrar denenebilir. (f) Backend 409
    ham detay'ı KULLANICIYA GÖSTERİLMEZ; kararlı belirteçlerle güvenli sabit mesajlara sınıflandırılır
    (not_blocked / no_assignment / candidate_inactive / genel). (g) Liste yalnız güvenli alanlar
    döndürür: talep başlığı ve requester e-postası backend'den GELMEZ. Talep sahibi e-postası (mevcutsa)
    üye listesinden eşlenir; eşleşmezse "Bilinmiyor" (uydurulmaz). Talep referansı kısa ID metni olarak
    gösterilir (link verilmedi — owner/admin'in keyfi PR'ı görme yetkisi doğrulanamadı; bilinen
    sınırlama). (h) Güvenlik: provider_subject/auth_provider/JWT frontend tiplerine/DOM'a alınmaz; ham
    backend response loglanmaz; task/member/assignment verisi ve target user_id browser storage'a
    yazılmaz. (i) Bu dilim approve/reject UI DEĞİLDİR, genel task reassignment sistemi DEĞİLDİR;
    approval-role configuration FP-FE-003'tedir; e-posta teslimi ve hosting kapsam dışıdır. Yeni
    state-yönetimi/UI kütüphanesi eklenmedi.
  impact: high
  reversible: true
  owner: product
  status: validated
  validation_method: >
    Ön inceleme (2026-07-24) resolve endpoint'inin kullanıcı seçimi kabul etmediğini (aday, mevcut
    aktif rol atamasından otomatik) ortaya çıkardı; owner, aday-seçim modalı yerine sözleşme-sadık
    seçimsiz onay akışını onayladı. Frontend blocked-task listeleme + tek-buton resolve, seçimsiz
    onay, concurrency'nin backend'de olması (frontend version göndermez), stale/çakışmanın otomatik
    retry edilmemesi, global assignment'ın değişmemesi ve frontend authz'ın UX-only olması doğrulandı.
    Backend/migration DEĞİŞMEDİ; alembic head 0011; release_verify tüm kapılar yeşil.
  expires_at: 2026-12-01
  affected_stories: [FP-FE-004]
  binding_rule: >
    Engellenen görev frontend'i resolve endpoint'ini KULLANICI SEÇİMİ OLMADAN çağırır (backend adayı
    mevcut aktif rol atamasından seçer; frontend user_id/version/idempotency göndermez, sahte aday/
    version üretmez). Görünürlük UX-only; backend policy tek kaynak (owner/admin; member 403; cross-
    tenant 404). Resolve yalnız seçili görevi etkiler; global approval-role assignment değişmez; UI
    approve/reject sunmaz. Her 409'da liste tazelenir, otomatik retry yok; ham backend detay'ı
    gösterilmez, güvenli sabit mesajlara sınıflandırılır. Talep başlığı/e-posta backend'den gelmediği
    için requester e-postası üye listesinden eşlenir (yoksa "Bilinmiyor"), talep kısa ID gösterilir.
    Hassas identity gösterilmez/loglanmaz; veri browser storage'a yazılmaz. Aday-seçim UI, approve/
    reject, genel reassignment, e-posta teslimi ve hosting kapsam dışıdır.
  reference: apps/web/src/features/blocked-tasks/actions.ts
```
