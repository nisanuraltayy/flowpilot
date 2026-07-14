# ADR-005 — Authentication Boundary: Supabase Auth + FlowPilot-Owned Authorization

- **Durum:** ✅ **Accepted**
- **Tarih:** 2026-07-14 (öneri) · **2026-07-14 (owner kararı: Supabase Auth)**
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-004 (**KAPANDI**)
- **İlgili PRD bölümleri:** §9.2, §9.3, §16.2, §17, §35.1
- **Kapatılan açık soru:** [OQ-001](../open-questions.md) ✅

> ℹ️ Karar verildi: **Supabase Auth**. Ancak gerçek entegrasyon **repository bootstrap onayı sonrasında** ve **yalnız `AuthProviderPort` adapter'ı olarak** yapılır. Bu doküman yazıldığı anda henüz hiçbir entegrasyon kodu yoktur.

---

## Bağlam

Authentication in-house yazılmayacak; **managed provider** kullanılacaktır. Bu, PRD'nin "in-house auth" seçeneğini kapatır (parola hash'leme, reset token, e-posta doğrulama, MFA, session revocation gibi güvenlik-kritik yüzeyleri kendimiz yazmayız).

**Kritik sınır kararı:** Organizasyon, membership, RBAC ve authorization **FlowPilot domain'inde** tutulur. Provider'ın "organizations"/"roles" özellikleri **kullanılmaz**.

Gerekçe:

- Yetki modeli ürünün çekirdeğidir (onay limitleri, self-approval engeli, field-level visibility, dört göz prensibi). Bunu bir kimlik sağlayıcısının veri modeline emanet etmek, ürünün en kritik mantığını dışarıya kiralamaktır.
- Provider değiştirilebilir kalmalıdır. Membership provider'da tutulursa geçiş maliyeti kabul edilemez olur.
- Cross-tenant izolasyon testleri ve RLS politikaları FlowPilot veritabanındaki membership'e dayanır.

Provider'ın sorumluluğu **yalnız** şudur: kullanıcının kim olduğunu doğrulamak ve doğrulanabilir bir token üretmek.

---

## Değerlendirilen seçenekler

Karar kriterleri ve iki adayın karşılaştırması:

| # | Kriter | Supabase Auth | Clerk |
|---|---|---|---|
| 1 | **FastAPI entegrasyonu** | Resmî Python SDK var; ancak asıl yol **JWT doğrulamasıdır** (JWKS ile imza doğrulama). Basit ve SDK'sız da yapılabilir. | Resmî Python SDK var; JWT doğrulaması JWKS ile yapılır. İkisi de FastAPI için "middleware + JWKS" desenine indirgenir. **Belirleyici fark yok.** |
| 2 | **Next.js entegrasyonu** | İyi (`@supabase/ssr`, server-side session). Kurulum biraz daha manuel. | **Çok güçlü** — Next.js birinci sınıf vatandaş; middleware, server component desteği hazır. **Clerk avantajlı.** |
| 3 | **JWT doğrulama** | Asimetrik imzalı JWT + JWKS endpoint. Backend, provider'a çağrı yapmadan offline doğrulayabilir. | Asimetrik imzalı JWT + JWKS endpoint. Offline doğrulama mümkün. **Eşit.** |
| 4 | **Organizasyon/membership modelinden bağımsız kullanılabilme** | **Evet.** Auth'u saf kimlik doğrulama olarak kullanmak doğaldır; org özelliği yok sayılabilir. | **Evet, ama dikkat.** Clerk'in Organizations özelliği güçlü ve cazip; kullanılmaması **disiplin gerektirir**. Yanlışlıkla bağımlılık kurma riski daha yüksek. **Supabase hafif avantajlı.** |
| 5 | **Vendor lock-in** | **Düşük.** Kullanıcı verisi kendi PostgreSQL'imizde (self-host edilebilir); açık kaynak, çıkış yolu net. | **Orta-yüksek.** Kullanıcı kayıtları Clerk'te yaşar; dışa aktarma mümkün ancak parola hash'leri taşınamaz (kullanıcılar reset'e zorlanır). **Supabase avantajlı.** |
| 6 | **Local development** | **Çok güçlü.** Supabase CLI ile tamamen local, ücretsiz, offline. Docker tabanlı stack'imize doğal uyar. | **Zayıf.** Local geliştirme bulut örneğine (dev instance) bağlıdır; tam offline çalışmaz. **Supabase belirgin avantajlı.** |
| 7 | **Maliyet** | Cömert ücretsiz kademe; MAU başına maliyet düşük. Self-host = altyapı maliyeti. | Ücretsiz kademe var; MAU ve özellik (özellikle organizations/SSO) bazında **daha pahalı ölçeklenir**. **Supabase avantajlı.** |
| 8 | **Güvenlik** | Olgun; MFA, e-posta doğrulama, reset akışları hazır. Güvenlik yükü büyük ölçüde provider'da. | Olgun; MFA, bot koruması, device management daha zengin. **Clerk hafif avantajlı.** |
| 9 | **Test edilebilirlik** | Local stack sayesinde integration test gerçek provider'a karşı çalıştırılabilir. | Fake adapter + contract test gerekir; gerçek provider'a karşı test bulut bağımlıdır. **Supabase avantajlı.** |
| 10 | **Gelecekte SSO (SAML/OIDC)** | Var; ancak SSO ücretli/kurumsal kademede. | **Daha olgun** kurumsal SSO ve SCIM hikâyesi. **Clerk avantajlı.** |
| 11 | **Veri barındırma ve KVKK** | **Belirleyici avantaj:** Self-host edilebilir; veri Türkiye'de veya seçilen bölgede tutulabilir. Bölge seçimi mümkün. | Veri sağlayıcının bölgelerinde tutulur; **veri yerleşimi üzerinde kontrol sınırlı**. KOBİ müşterilerin "hangi veriler cloud'a çıkamaz" sorusuna cevap vermek zorlaşır. **Supabase belirgin avantajlı.** |

### Skor özeti

- **Clerk'in üstün olduğu:** Next.js DX (2), güvenlik özellik zenginliği (8), kurumsal SSO olgunluğu (10).
- **Supabase'in üstün olduğu:** provider bağımsızlığı (4), vendor lock-in (5), local development (6), maliyet (7), test edilebilirlik (9), **veri barındırma / KVKK (11)**.

---

## Karar

> ✅ **Supabase Auth seçildi.** (Owner kararı, 2026-07-14)

**Supabase yalnızca authentication sağlayıcısıdır.** Organization, membership, manager hierarchy, RBAC, authorization ve tenant modeli **FlowPilot domain'inde ve FlowPilot'ın PostgreSQL veritabanında** tutulur. Supabase'in organizations/roles özellikleri **kullanılmaz**.

Gerekçe sıralaması:

1. **KVKK ve veri barındırma (kriter 11).** Hedef müşteri Türkiye merkezli KOBİ'dir ve PRD, kullanıcı araştırmasında açıkça "Hangi veriler cloud'a çıkamaz?" sorusunu sormaktadır. Self-host edilebilir bir kimlik katmanı, bu itirazı karşılayabilen **tek** seçenektir. Bu kriter geri döndürülmesi en pahalı olandır.
2. **Local development (kriter 6).** Docker tabanlı, provider-neutral geliştirme ortamı hedefiyle (MinIO, PostgreSQL) doğal uyum. Solo developer için offline çalışabilmek somut bir hız kazancıdır.
3. **Vendor lock-in (kriter 5).** Parola hash'lerinin taşınamaması, Clerk'ten çıkışı tüm kullanıcıları parola sıfırlamaya zorlayan bir olaya çevirir. Bu, gerçek bir çıkış maliyetidir.
4. Clerk'in en güçlü kozu (Next.js DX) **bir kereye mahsus kurulum konforudur**; ürün ömrü boyunca tekrar tekrar ödenmez. Veri yerleşimi ise sürekli ödenir.

**Clerk'in tercih edilmesi gereken durum (gerçekleşmedi):** İlk pilot müşteriler kurumsal SSO/SCIM'i MVP'de şart koşsaydı ve veri yerleşimi bir itiraz olarak gelmeseydi, kriter 10 ve 2, kriter 11'i geçebilirdi.

---

## Sonuçlar

**Pozitif**

- Veri yerleşimi (KVKK) üzerinde kontrol; self-host seçeneği açık.
- Local development tamamen offline ve ücretsiz; Docker tabanlı geliştirme ortamıyla doğal uyum.
- Düşük vendor lock-in; çıkış maliyeti yönetilebilir.
- Integration testler gerçek provider'a karşı local'de çalıştırılabilir.

**Negatif / risk**

- **Next.js entegrasyon DX'i Clerk kadar hazır değil** — server-side session kurulumu daha manuel. Bir kereye mahsus maliyet olarak kabul edildi.
- **En büyük risk: Supabase'in kolaylığına kayma.** Supabase yalnız bir kimlik sağlayıcısı değil, bir PostgreSQL platformudur. Supabase'in kendi veritabanını, RLS'ini veya org modelini FlowPilot'ın domain veritabanı yerine kullanmaya kayma cazibesi gerçektir ve bu, aşağıdaki uyum kurallarının en kritik olanını ihlal eder.
- Kurumsal SSO/SCIM gerektiğinde Supabase'in kurumsal kademesi devreye girer (maliyet).

---

## Uyum kuralları (agent için bağlayıcı)

1. **Supabase YALNIZCA authentication sağlayıcısıdır.** Kullanıcının kim olduğunu doğrular ve token üretir. Başka hiçbir sorumluluğu yoktur.
2. **Organization, membership, manager hierarchy, RBAC, authorization ve tenant modeli FlowPilot domain'inde ve FlowPilot'ın PostgreSQL veritabanındadır.** Supabase'in organizations/roles/permissions özelliklerine **bağımlılık kurulamaz**.
3. **Domain katmanı Supabase SDK'sına doğrudan bağımlı olamaz.** Supabase entegrasyonu **yalnız `AuthProviderPort` adapter'ı** içinde bulunur.
4. Supabase'in veritabanı, RLS motoru veya PostgREST katmanı FlowPilot'ın operasyonel veritabanı **olarak kullanılamaz**. FlowPilot'ın kendi PostgreSQL şeması, kendi RLS politikaları (ADR-006) ve kendi migration'ları (Alembic) vardır.
5. Provider `sub` claim'i FlowPilot `users.external_auth_id` alanına eşlenir. E-posta primary key **değildir**.
6. Token her istekte doğrulanır: imza (JWKS), issuer, audience, expiry. Doğrulanmamış claim yetki kaynağı olamaz.
7. `AuthProviderPort`'un fake adapter'ı ve Supabase adapter'ı **aynı contract test setini** geçer. Testler fake adapter ile çalışabilmelidir.
8. Doğrulanmamış e-postaya sahip kullanıcı tenant verisine erişemez.
9. **Bu mesaj kapsamında gerçek Supabase entegrasyonu YAPILMAMIŞTIR** ve repository bootstrap onayı gelene kadar yapılmayacaktır.

## Yeniden değerlendirme tetikleyicileri

- Pilot müşteri SSO/SCIM'i şart koşar ve Supabase'in kurumsal kademesi maliyet olarak orantısız kalırsa.
- Supabase Auth'un Next.js entegrasyonu sürdürülemez bir bakım yükü üretirse.
- Veri yerleşimi gereksinimi self-host'u zorunlu kılarsa (bu durumda karar güçlenir, değişmez).

## İlgili dokümanlar

- Kapsam: [docs/product/mvp-scope-v0.1.md](../product/mvp-scope-v0.1.md)
- Port kuralları: [docs/architecture/dependency-rules.md](../architecture/dependency-rules.md)
- Story'ler: FP-E01-001 (karar — done), FP-E01-002 (port + adapter), FP-E01-003 (actor context)
