# Veritabanı Kuralları

Bağlayıcı kaynak: PRD §13, §37, §40 ve ADR-006, ADR-007.

Veritabanı: **PostgreSQL** — operasyonel tek source of truth.
ORM/migration: **SQLAlchemy + Alembic** (ADR-001). ORM modelleri yalnız infrastructure katmanında bulunur.

---

## 1. Tenant izolasyonu (şema seviyesi)

- Tenant verisi taşıyan **her** tablo `tenant_id` kolonuna sahiptir. İstisna (global tablo) açıkça işaretlenir ve fitness check'te whitelist'lenir.
- Her tenant tablosunda **PostgreSQL Row Level Security** politikası tanımlıdır (ADR-006). RLS, uygulama filtresinin yerine değil, **ikinci savunma katmanı** olarak bulunur.
- Uygulama, DB session'ını tenant context ile açar; tenant değeri istemci gövdesinden alınmaz.
- Composite index'ler `tenant_id` ile **başlar** (`(tenant_id, status, created_at)` gibi).
- Migration'lar RLS politikalarını da versiyonlar; yeni tenant tablosu RLS politikası olmadan merge edilemez.

---

## 2. Para ve zaman

**Para:**

- **YASAK:** `FLOAT`, `DOUBLE PRECISION`, Python `float`.
- **ZORUNLU:** Minor unit (integer, örn. kuruş) + ISO-4217 `currency` kolonu. İki kolon **birlikte** taşınır; para birimi olmayan tutar geçersizdir.
- Farklı para birimlerinde tutar toplama/karşılaştırma domain'de açıkça reddedilir.
- Koşul değerlendirmesi (örn. `amount > 50000`) minor unit üzerinden deterministik yapılır.

**Zaman:**

- Tüm timestamp'ler **UTC** saklanır (`TIMESTAMPTZ`).
- Naive datetime **YASAK**.
- Organizasyon timezone'u yalnız gösterim ve business calendar hesabında kullanılır.
- İşlem süresi ölçümünde wall-clock yerine monotonic clock kullanılır.

---

## 3. Kimlik

- Public identifier: **UUID veya ULID**. Sıralı DB ID dışarı açılmaz.
- E-posta adresi kullanıcının değişmez primary key'i **değildir**.
- İsim, rol veya departman metni tarihsel kayıtlarda serbest metin olarak değil; ID referansı + snapshot metadata ile saklanır.

---

## 4. JSONB kullanımı

**JSONB kullanılabilir:**

- Workflow node config
- Form schema
- Event metadata
- Provider'a özgü, sorgulanmayan config

**JSONB içinde saklanamaz:**

- `tenant_id`
- State/status
- Owner/assignee
- Due date
- Tutar/para birimi
- Permission ilişkileri
- Sık filtrelenen alanlar
- Unique constraint gerektiren alanlar

Her JSON belge **versiyonlu JSON Schema** ile doğrulanır. Şemasız serbest blob domain **YASAK**.

---

## 5. Transaction sınırları

Güçlü transaction gerektiren işlemler:

- Tenant, membership, permission değişiklikleri
- Workflow publish (immutable version + hash + audit **atomik**)
- Approval decision (karar + step state + outbox + audit **aynı transaction**)
- Workflow instance state transition (state + outbox + audit **aynı transaction**)

Eventual consistency kabul edilebilir: notification teslimi, analytics aggregate, timeline projection.

Kullanıcıya "işlem tamamlandı" cevabı verildiyse source-of-truth transaction **commit edilmiş** olmalıdır.

---

## 6. Outbox ve idempotency

- `outbox_events` tablosu: business state ile **aynı transaction'da** yazılır.
- Dispatcher: PostgreSQL-backed polling worker; `FOR UPDATE SKIP LOCKED` benzeri lease mekanizmasıyla çoklu worker güvenliği sağlar.
- İşlenen event işaretlenir; consumer tarafında `processed_events` / inbox kaydı ile **duplicate side effect** engellenir.
- Dual write **YASAK**.
- `idempotency_keys` tablosu: mutating public API'ler için `tenant + actor + endpoint + request fingerprint` scope'unda.
- Aynı idempotency key farklı payload ile gelirse **conflict** döner.

---

## 7. Optimistic concurrency

Mutasyona açık her aggregate'te `version` (veya `updated_at` + ETag) alanı bulunur:

- `workflow_drafts`, `tasks`, `approval_steps`, `workflow_instances`, `purchase_requests`, `organization_settings`
- Stale write → `409 Conflict` / `412 Precondition Failed`
- Approval kararında duplicate koruması için ek olarak **unique constraint** (`approval_step_id` başına tek terminal decision) bulunur.

---

## 8. Migration politikası

**Expand → Deploy → Backfill → Switch → Verify → Contract** sırası zorunludur:

1. **Expand:** Yeni nullable kolon/tablo/index ekle.
2. **Deploy:** Eski ve yeni şema ile çalışan kod.
3. **Backfill:** Tekrarlanabilir, chunk'lı, gözlemlenebilir job. **Web request içinde backfill YASAK.**
4. **Switch:** Kontrollü rollout.
5. **Verify:** Count, checksum, business invariant kontrolü.
6. **Contract:** Eski kolon/constraint **sonraki** release'te kaldırılır.

Kurallar:

- Migration production'da uzun table lock yaratmaz. Büyük index `CONCURRENTLY` oluşturulur.
- Migration forward-only davranır; rollback planı application rollback + forward fix'tir.
- **Migration dosyası silinip yeniden üretilmez.**
- **Migration ile veri silme agent'in bağımsız kararı değildir** (owner onayı gerekir).
- Migration CI'da boş DB **ve** bir önceki release şeması üzerinde test edilir.
- Seed ve fixture ayrılır; production verisi seed'e gömülmez.
- Destructive migration tek deploy'da yapılmaz.

---

## 9. Index ve sorgu politikası

- Index gerçek query pattern'e dayanır; spekülatif index eklenmez.
- Her list endpoint'i `tenant_id` ile başlayan uygun composite index'e sahiptir.
- Dashboard sorguları operasyonel tabloları yavaşlatmaz; özet tablo / materialized view / read model kullanır.
- N+1 sorgu **YASAK**; projection ve batching kullanılır.
- Unbounded list **YASAK**; cursor pagination + server-side max page size.

---

## 10. Yaşam döngüsü ve silme

- "Soft delete everywhere" **YASAK**. Kaynak bazlı lifecycle tanımlanır.
- Tenant silme: `active → scheduled_for_deletion → export penceresi → grace period → veri silme/anonimleştirme` şeklinde **idempotent ve resumable saga** olarak tasarlanır (MVP'de tasarım hazır olur; implementasyon E12 kapsamındadır).
- Audit kayıtları normal iş tablosu güncelleme yoluyla **değiştirilemez**; retention politikasına tabidir.
- **YASAK:** Production'da ham SQL ile manuel veri düzeltme. Versiyonlu admin repair command'ı (dry-run + audit) kullanılır.
