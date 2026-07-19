# Açık Kararlar (Open Questions)

Owner kararı bekleyen konular. Agent bu kararları **kendi başına veremez** (AGENTS.md §4).

Bir OQ kapandığında: karar bir ADR'ye veya kapsam dokümanına yazılır, ilgili kilit kapatılır, kayıt "Kapanan kararlar" bölümüne taşınır.

**Son güncelleme:** 2026-07-15 — canlı Supabase kabul testiyle **OQ-009 ve OQ-010 kapandı**.

| Kimlik | Konu | Kilit | Etki | Durum |
|---|---|---|---|---|
| OQ-002 | Hosting sağlayıcısı ve veri bölgesi | LOCK-006 | Orta | 🔴 **Açık** |
| OQ-003 | Repository bootstrap yürütme onayı | — | Yüksek | 🟡 **Prensipte onaylandı — komut bekleniyor** |
| OQ-004 | Onay eşiklerinin gerçek müşteride doğrulanması | — | Düşük | 🟡 **Geçici varsayım olarak kaydedildi** |
| OQ-008 | AI provider ve veri politikası | LOCK-007 | Düşük | 🔴 Açık (MVP dışı — aciliyet yok) |
| OQ-001 | Auth provider | LOCK-004 | — | ✅ **KAPANDI — Supabase Auth** |
| OQ-005 | PRD MVP listesi ile gerçek MVP kapsamı farkı | — | — | ✅ **KAPANDI** |
| OQ-006 | E-posta bildirimi | — | — | ✅ **KAPANDI — pilot-ready** |
| OQ-007 | Zararlı dosya taraması | — | — | ✅ **KAPANDI — pilot-ready güvenlik kriteri** |
| OQ-009 | Canlı Supabase JWT kabul testi (backend) | — | — | ✅ **KAPANDI — canlı kabul testi geçti (2026-07-15)** |
| OQ-010 | Canlı Supabase login/signup + uçtan uca frontend (web) | — | — | ✅ **KAPANDI — canlı kabul testi geçti (2026-07-15)** |

---

## 🔴 Açık kararlar

### OQ-002 — Hosting sağlayıcısı ve veri bölgesi

**Durum:** 🔴 Açık
**Kilit:** LOCK-006

**Soru:** Production hangi sağlayıcıda ve hangi veri bölgesinde çalışacak? İlk aday **Render**.

**Bağlantı:** Supabase Auth seçildi (OQ-001). Supabase self-host edilebilir olduğu için veri yerleşimi (KVKK) üzerinde kontrol mümkün — ancak *managed Supabase* mi *self-host Supabase* mi kullanılacağı bu kararla birlikte netleşmelidir.

**Karar verilene kadar agent ne yapar:** Deployment **provider-neutral** kalır (Docker tabanlı). Sağlayıcıya özgü manifest, buildpack veya SDK eklenmez.

**MVP'yi bloke eder mi:** Hayır. Local MVP tamamen local çalışır. Pilot-ready öncesinde karar gerekir.

---

### OQ-008 — AI provider ve veri politikası

**Durum:** 🔴 Açık
**Kilit:** LOCK-007

**Soru:** AI özellikleri geldiğinde hangi provider ve hangi veri işleme politikası kullanılacak?

**Aciliyet:** Yok. AI özellikleri hem Local MVP hem pilot-ready kapsamı dışındadır.

**Karar verilene kadar agent ne yapar:** AI ile ilgili **hiçbir kod yazılmaz**. Provider abstraction bile MVP kapsamında değildir.

---

## 🟡 Koşullu / izlemede

### OQ-003 — Repository bootstrap yürütme onayı

**Durum:** 🟡 **Prensipte onaylandı** — yürütme komutu bekleniyor

**Owner kararı (2026-07-14):** *"Repository bootstrap prensip olarak onaylandı. Ancak bu mesaj kapsamında henüz bootstrap yapma."*

**Mevcut durum:** Repository **yalnızca dokümantasyon** içeriyor. Kod, dependency, `pyproject.toml`, `package.json`, `Dockerfile`, migration, git repository ve Supabase entegrasyonu **yok**.

**Bootstrap için gereken tüm kararlar artık kapalı:**

- ✅ Backend stack (ADR-001)
- ✅ Frontend stack (ADR-002)
- ✅ Monorepo (ADR-008)
- ✅ Auth provider (ADR-005 — Supabase)
- ✅ Kapsam (mvp-scope-v0.1.md)
- ⚠️ Hosting (OQ-002) — **bloke etmez**; deployment provider-neutral kalır

**Bekleyen:** Owner'ın açık bootstrap komutu.

---

### OQ-004 — Onay eşiklerinin gerçek müşteride doğrulanması

**Durum:** 🟡 Geçici ürün varsayımı olarak kaydedildi
**İlgili varsayım:** [ASM-0001](assumptions.md)

**Owner kararı (2026-07-14):** Demo ve ilk dikey dilim için varsayılan eşikler:

| Tutar | Onay zinciri |
|---|---|
| < 10.000 TL | Ekip yöneticisi |
| 10.000 – 50.000 TL | Ekip yöneticisi → Finans |
| > 50.000 TL | Ekip yöneticisi → Finans → Genel Müdür |

**Bağlayıcı kural:** Bu değerler **domain koduna hard-code edilemez**; workflow definition içindeki `Condition` node koşullarından gelir.

**Açık kalan:** Bu eşiklerin gerçek KOBİ'lerde doğru olup olmadığı. Doğrulama: pilot müşteri görüşmesi. **Yanlış çıkması kod değişikliği gerektirmez** — yalnız yeni bir workflow version yayınlanır.

---

## ✅ Kapanan kararlar

### OQ-009 — Canlı Supabase JWT kabul testi (backend) ✅ KAPANDI

**Kapanış (2026-07-15):** Canlı Supabase projesiyle uçtan uca kabul testi **geçti**.

Kanıt özeti (secret veya kişisel veri içermez):

- Gerçek Supabase signup, e-posta doğrulaması ve gerçek login owner tarafından tarayıcıdan yapıldı.
- Canlı projenin public JWKS'i tek **ES256** (EC P-256, `use=sig`) imza anahtarı servis etti; `SupabaseJwtAuthAdapter` gerçek access token'ı bu anahtarla doğruladı (`SUPABASE_JWT_ALLOWED_ALGORITHMS=ES256`).
- Gerçek token ile `POST /v1/organizations` → **HTTP 201**.
- Claim eşlemesi doğru çalıştı: `identity_users` kaydı `auth_provider=supabase` + dolu `provider_subject` ile oluştu; e-posta yalnız snapshot olarak tutuldu.
- Risk notundaki en olası sapma (issuer/audience varsayılanları) **gerçekleşmedi**; varsayılan yapılandırma canlı projeyle birebir uyumlu çıktı.

---

### OQ-010 — Canlı Supabase login/signup ve uçtan uca frontend kabul testi ✅ KAPANDI

**Kapanış (2026-07-15):** OQ-009 ile aynı canlı kabul testinde **geçti**.

Kanıt özeti (secret veya kişisel veri içermez):

- `apps/web/.env.local` gerçek proje URL'i ve publishable key ile yapılandırıldı (git-ignored; hiçbir değer repository'ye girmedi).
- Gerçek kullanıcıyla signup → `/auth/check-email` → e-posta doğrulama linki → `/auth/callback` → login akışı canlı Supabase ile çalıştı.
- Onboarding'den **"FlowPilot Test Şirketi"** organizasyonu oluşturuldu (açıkça test verisi olarak adlandırıldı); server action → Bearer token → FastAPI → 201 → başarı ekranı.
- Veritabanında tenant (`status=active`) ve **aktif owner membership** (`role=owner`, `status=active`) oluştu; organizasyon ve membership **aynı transaction'da** yazıldı (`created_at` değerleri mikrosaniye düzeyinde eşit).
- Risk notundaki olası sapmalar (confirm email ayarı, callback URL yapılandırması) sorun çıkarmadı.

---

### OQ-001 — Auth provider ✅ KAPANDI

**Karar (2026-07-14):** **Supabase Auth.**

- Supabase **yalnızca authentication sağlayıcısıdır**.
- Organization, membership, manager hierarchy, RBAC, authorization ve tenant modeli **FlowPilot domain'inde ve FlowPilot'ın PostgreSQL veritabanında** tutulur.
- Domain katmanı **Supabase SDK'sına doğrudan bağımlı olamaz**.
- Supabase entegrasyonu **`AuthProviderPort` adapter sınırı arkasındadır**.
- Supabase'in veritabanı/RLS'i FlowPilot'ın operasyonel veritabanı olarak **kullanılamaz**.

**Kilit:** LOCK-004 **kapandı**. **ADR:** [ADR-005](adr/ADR-005-authentication-boundary.md) → `Accepted`.

**Not:** Gerçek entegrasyon **repository bootstrap onayı sonrasında** yapılacaktır; bu mesaj kapsamında yapılmamıştır.

---

### OQ-005 — PRD MVP listesi ile gerçek MVP kapsamı farkı ✅ KAPANDI

**Karar (2026-07-14):**

- **PRD değiştirilmez.** §7.1 ve §24 dahil, PRD araştırma ve uzun vadeli ürün vizyonu olarak korunur.
- Bağlayıcı teslim kapsamı için yeni doküman oluşturuldu: **[docs/product/mvp-scope-v0.1.md](product/mvp-scope-v0.1.md)**.
- Bu doküman PRD'deki geniş MVP tanımının **üzerinde** önceliğe sahiptir.
- PRD'nin **mühendislik kuralları** (invariant'lar, anti-pattern'ler, state machine'ler, güvenlik gereksinimleri, §32–§48) **tam olarak bağlayıcı kalır** — kapsam dokümanı bunları gevşetmez.

---

### OQ-006 — E-posta bildirimi ✅ KAPANDI

**Karar (2026-07-14):** E-posta bildirimi **Local MVP kapsamı dışı**, **pilot-ready kapsamında**.

**Bağlayıcı kural:** `NotificationChannelPort` **şimdiden** provider-neutral (kanal-nötr) tasarlanır. MVP'de yalnız **in-app adapter** uygulanır. E-posta eklemek bir **adapter eklemek** olmalıdır — bir refactor değil.

**Kabul edilen risk:** Onaycı uygulamaya girmezse bekleyen onayı fark etmeyebilir. Bu risk owner tarafından bilinçli olarak kabul edilmiş ve pilot-ready çıkış kriteri olarak kayda geçirilmiştir ([ASM-0010](assumptions.md)).

---

### OQ-007 — Zararlı dosya taraması ✅ KAPANDI

**Karar (2026-07-14):**

- Gerçek tarama entegrasyonu **Local MVP çıkış kriteri DEĞİLDİR**.
- **Pilot-ready sürümün ZORUNLU güvenlik çıkış kriteridir.**
- Dosya modülü **başlangıçtan itibaren `MalwareScanPort`'u destekleyecek şekilde tasarlanır**; MVP'de yalnız no-op/stub adapter bulunur. `scan_status` alanı ve tarama tamamlanmadan indirmeyi engelleyen kapı şimdiden hazırdır.

**Sonuç:** Local MVP **pilot müşteriye açılmaz**. Gerçek müşteri verisi işlenmeden önce tarama entegre edilmiş olmalıdır ([ASM-0007](assumptions.md)).

---

## Kapanan teknoloji kararları (ADR özeti)

| Konu | Karar | ADR | Kilit |
|---|---|---|---|
| Backend stack | Python + FastAPI + Pydantic + SQLAlchemy + Alembic | ADR-001 | LOCK-001 ✅ |
| Frontend stack | Next.js + TypeScript | ADR-002 | LOCK-002 ✅ |
| Mimari | Modüler monolit | ADR-003 | — |
| Workflow runtime | Custom PostgreSQL-backed, port arkasında; **spike 12/12 PASS (2026-07-19)**. Camunda 8 elendi; Temporal yedek | ADR-004 | LOCK-003 ✅ |
| Authentication | **Supabase Auth** — yalnız kimlik doğrulama. Org/membership/RBAC/tenant FlowPilot domain'inde | ADR-005 | LOCK-004 ✅ |
| Tenant izolasyonu | Application scope + PostgreSQL RLS | ADR-006 | — |
| Asenkron işlem | Transactional outbox + PostgreSQL polling worker | ADR-007 | LOCK-005 ✅ |
| Repository | Monorepo | ADR-008 | LOCK-008 ✅ |
