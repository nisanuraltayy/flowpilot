# ADR-006 — Tenant İzolasyonu: Application-Level Scope + PostgreSQL Row Level Security

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** —
- **İlgili PRD bölümleri:** §9.1, §13, §16.3, §36.1, §40

## Bağlam

Cross-tenant veri sızıntısı, çok kiracılı bir SaaS için **kritik** ve itibar açısından geri döndürülemez risktir (PRD §27: Etki=Kritik). FlowPilot'ta form cevapları, onay kararları, maaş/satın alma tutarları ve organizasyon hiyerarşisi gibi hassas veriler işlenir.

PRD'nin normatif kuralı: *"Tenant filtresi geliştiricinin hatırlamasına bırakılamaz."*

## Değerlendirilen seçenekler

| Seçenek | Açıklama | Değerlendirme |
|---|---|---|
| A. Yalnız application-level filtre | Her sorguya `WHERE tenant_id = :ctx` eklenir | **Yetersiz.** Tek bir unutulmuş `WHERE` = sızıntı. Ham SQL, raporlama sorgusu, admin script'i bu katmanı atlar. |
| B. Yalnız PostgreSQL RLS | Politika veritabanında zorlanır | Güçlü ama tek başına kırılgan: yanlış rol/bağlantı ile bypass edilebilir, uygulama hataları geç fark edilir, performans/plan etkisi görünmez olur. |
| C. **Her ikisi (defense-in-depth)** | Application scope **ve** RLS | **Seçilen.** İki bağımsız katmanın **aynı anda** hata yapması gerekir. |
| D. Tenant başına ayrı şema/veritabanı | Fiziksel izolasyon | En güçlü izolasyon; ancak migration, connection pool ve operasyon maliyeti 100+ tenant'ta orantısız. MVP için reddedildi. |

## Karar

**Seçenek C — defense-in-depth:**

1. **Katman 1 — Application scope.** Tenant filtresi repository/session boundary'sinde **otomatik** uygulanır. Handler'lar tenant filtresini elle yazmaz ve hatırlamak zorunda kalmaz.
2. **Katman 2 — PostgreSQL Row Level Security.** Tenant verisi taşıyan her tabloda RLS politikası tanımlıdır. Uygulama, DB session'ını tenant context ile açar; RLS politikası satırları veritabanı seviyesinde filtreler.
3. **Katman 3 — Test.** Cross-tenant regression suite; API, cache, arama, dosya ve read model sınırlarını otomatik doğrular.

`TenantContext` request/worker başında **bir kez** çözülür ve istemci gövdesinden **asla** okunmaz.

## Gerekçe

- Tek katman her zaman insan hatasına açıktır. RLS, unutulmuş bir `WHERE`'i sessiz sızıntıya değil, boş sonuç kümesine çevirir.
- Aynı veritabanında custom workflow runtime çalıştığı için (ADR-004) RLS politikası runtime sorgularını da kapsar; harici bir runtime'da bu güvence olmazdı.
- Şema-per-tenant'ın operasyon maliyeti MVP ölçeğinde (100 tenant hedefi) gerekçelendirilemez.

## Sonuçlar

**Pozitif**

- İki bağımsız savunma katmanı; sızıntı için iki ayrı hata gerekir.
- RLS, ham SQL ve raporlama sorgularını da kapsar.
- Aynı DB'de çalışan worker ve runtime da korunur.

**Negatif / risk**

- RLS politikaları **yanlış yazılırsa** sessizce ya çok kısıtlar (veri "kayboldu" gibi görünür) ya da hiç kısıtlamaz. → Her tenant tablosu için RLS'in gerçekten uygulandığını doğrulayan **integration test zorunludur**.
- RLS query plan'ı etkileyebilir → kritik endpoint'lerde plan regresyonu izlenir.
- Migration'lar RLS politikalarını da versiyonlamak zorundadır (ek disiplin).
- Worker/superuser bağlantıları RLS'i bypass edebilir → **`BYPASSRLS` yetkisine sahip rol uygulama tarafından kullanılmaz.**

## Uyum kuralları (agent için bağlayıcı)

1. Tenant verisi taşıyan **her** tablo `tenant_id` içerir. İstisna açıkça whitelist'lenir ve gerekçelendirilir.
2. Yeni tenant tablosu **RLS politikası olmadan merge edilemez**; migration politikayı da içerir.
3. Uygulama, veritabanına **`BYPASSRLS` yetkisi olan rolle bağlanamaz**.
4. Tenant kimliği istemciden gelen gövde/parametreden okunamaz; doğrulanmış token → membership → `TenantContext` zincirinden çözülür.
5. Cache key'leri, arama sorguları ve object storage yolları tenant ile ayrılır.
6. Tenant verisine dokunan **her** story'de cross-tenant negatif test bulunur (IDOR/BOLA).
7. Cross-tenant erişim denemesi kaynağın varlığını sızdırmaz ve güvenlik log'una yazılır.
8. Composite index'ler `tenant_id` ile başlar.

## Yeniden değerlendirme tetikleyicileri

- Tek bir tenant'ın veri hacmi diğerlerini ezip izolasyon/performans sorunu üretirse (şema-per-tenant yeniden değerlendirilir).
- RLS'in ölçülebilir bir performans tavanı yarattığı kanıtlanırsa.
- Bir müşteri sözleşmesi fiziksel izolasyon şart koşarsa.
