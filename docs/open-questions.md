# Açık Kararlar (Open Questions)

Owner kararı bekleyen konular. Agent bu kararları **kendi başına veremez** (AGENTS.md §4).

Bir OQ kapandığında: karar bir ADR'ye veya kapsam dokümanına yazılır, ilgili kilit kapatılır, kayıt "Kapanan kararlar" bölümüne taşınır.

**Son güncelleme:** 2026-07-14 — owner kararlarıyla **5 karar kapandı**.

| Kimlik | Konu | Kilit | Etki | Durum |
|---|---|---|---|---|
| OQ-002 | Hosting sağlayıcısı ve veri bölgesi | LOCK-006 | Orta | 🔴 **Açık** |
| OQ-003 | Repository bootstrap yürütme onayı | — | Yüksek | 🟡 **Prensipte onaylandı — komut bekleniyor** |
| OQ-004 | Onay eşiklerinin gerçek müşteride doğrulanması | — | Düşük | 🟡 **Geçici varsayım olarak kaydedildi** |
| OQ-008 | AI provider ve veri politikası | LOCK-007 | Düşük | 🔴 Açık (MVP dışı — aciliyet yok) |
| OQ-009 | Canlı Supabase JWT kabul testi (backend) | — | Orta | 🔴 **Açık — credential bekleniyor** |
| OQ-010 | Canlı Supabase login/signup + uçtan uca frontend (web) | — | Orta | 🔴 **Açık — OQ-009 ile aynı credential'la kapanır** |
| OQ-001 | Auth provider | LOCK-004 | — | ✅ **KAPANDI — Supabase Auth** |
| OQ-005 | PRD MVP listesi ile gerçek MVP kapsamı farkı | — | — | ✅ **KAPANDI** |
| OQ-006 | E-posta bildirimi | — | — | ✅ **KAPANDI — pilot-ready** |
| OQ-007 | Zararlı dosya taraması | — | — | ✅ **KAPANDI — pilot-ready güvenlik kriteri** |

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

### OQ-009 — Canlı Supabase kabul testi

**Durum:** 🔴 Açık — gerçek Supabase projesi/credential bekleniyor

**Tespit:** `SupabaseJwtAuthAdapter` production-ready yazıldı ve network'süz
testlerle (runtime'da üretilen RSA/EC anahtarları + lokal JWKS) imza, exp, iss,
aud, sub, algoritma allow-list, HS256 reddi, key rotation ve cache dahil
kapsamlı doğrulandı. Ancak **canlı bir Supabase projesine karşı uçtan uca kabul
testi henüz YAPILMADI** — elde gerçek proje URL'i ve access token yok.

**Gereken:** Bir Supabase projesi oluşturulduğunda:
1. `.env` içine gerçek `SUPABASE_URL` yazılır.
2. O projeden bir kullanıcıyla access token alınır (frontend login aşaması bunu
   doğal olarak sağlayacak).
3. `POST /v1/organizations` gerçek token ile çağrılır; 201 + doğru claim
   eşlemesi doğrulanır.

**Risk:** Düşük-orta. JWKS formatı ve claim yapısı Supabase dokümantasyonuna
göre kodlandı; en olası sapma noktaları issuer/audience varsayılanlarıdır ve
ikisi de yapılandırılabilir.

**Zamanlama:** Frontend + Supabase login aşamasında doğal olarak kapanır.

---

### OQ-010 — Canlı Supabase login/signup ve uçtan uca frontend kabul testi

**Durum:** 🔴 Açık — gerçek Supabase projesi/credential bekleniyor (OQ-009'un frontend tarafı)

**Tespit:** Next.js web uygulaması (login/signup/onboarding) production-ready yazıldı ve şu doğrulamalar geçti: 49 birim testi, ESLint, strict typecheck, production build ve credential'sız smoke (`/login` ve `/signup` 200 render, korumalı `/dashboard` → `/login` 307). Ancak **canlı Supabase ile gerçek kayıt/giriş ve gerçek access token'la uçtan uca `POST /v1/organizations` akışı DOĞRULANMADI** — elde gerçek proje URL'i ve publishable key yok.

**Gereken:** Supabase projesi hazır olduğunda:
1. `apps/web/.env.local` içine `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (git-ignored).
2. `FLOWPILOT_API_BASE_URL` backend'e işaret eder (varsayılan `http://127.0.0.1:8000`).
3. `npm run dev` + backend `uvicorn`; gerçek bir test kullanıcısıyla signup/login yapılır.
4. Onboarding'de organizasyon oluşturulur; oluşan organization açıkça **test verisi** olarak işaretlenir.

**Risk:** Düşük-orta. Cookie/SSR akışı `@supabase/ssr`'ın güncel convention'ıyla kodlandı; en olası sapma, e-posta doğrulama ayarları (Supabase projesinde "confirm email" açık/kapalı) ve callback URL yapılandırmasıdır.

**Bağlantı:** OQ-009 (backend JWT kabul testi) ile aynı credential'la birlikte kapanır.

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
| Workflow runtime | Custom PostgreSQL-backed, port arkasında, **spike şartına bağlı**. Camunda 8 elendi; Temporal yedek | ADR-004 | LOCK-003 (koşullu) |
| Authentication | **Supabase Auth** — yalnız kimlik doğrulama. Org/membership/RBAC/tenant FlowPilot domain'inde | ADR-005 | LOCK-004 ✅ |
| Tenant izolasyonu | Application scope + PostgreSQL RLS | ADR-006 | — |
| Asenkron işlem | Transactional outbox + PostgreSQL polling worker | ADR-007 | LOCK-005 ✅ |
| Repository | Monorepo | ADR-008 | LOCK-008 ✅ |
