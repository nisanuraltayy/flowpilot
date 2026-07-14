# ADR-002 — Frontend Stack: Next.js + TypeScript

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-002 (**kapandı**)
- **İlgili PRD bölümleri:** §26, §43

## Bağlam

PRD frontend için React SPA, Next.js ve Vue/Nuxt adaylarını bırakmıştı. Değerlendirme kriterleri: workflow canvas kütüphaneleri, form builder, server rendering ihtiyacı, auth yaklaşımı ve dashboard performansı.

**Önemli kapsam daralması:** Görsel workflow builder canvas **gerçek MVP dışındadır**. Bu, "canvas kütüphanesi ekosistemi" kriterinin ağırlığını düşürür; MVP frontend'i esas olarak form, liste/inbox, onay ekranı, timeline ve dashboard'dur.

## Değerlendirilen seçenekler

| Kriter | Next.js + TS | React SPA (Vite) + TS | Vue/Nuxt |
|---|---|---|---|
| Auth entegrasyonu (managed provider) | **En güçlü** (Supabase/Clerk birinci sınıf Next.js desteği) | Orta | Orta |
| Server-side rendering / server components | Var | Yok | Var |
| Hassas veriyi sunucuda tutma | **Güçlü** (token/session server tarafında) | Zayıf (her şey client'ta) | Güçlü |
| Route/IA eşlemesi (PRD §43.1) | Doğrudan | Manuel router | Doğrudan |
| Dashboard ilk yükleme (p95 < 2.5s) | SSR avantajı | Client-side fetch dezavantajı | SSR avantajı |
| Ekosistem/istihdam (TR) | Yüksek | Yüksek | Orta |
| Karmaşıklık | Orta-yüksek (RSC/server actions öğrenme eğrisi) | Düşük | Orta |

## Karar

Frontend: **Next.js + TypeScript**.

## Gerekçe

1. **Auth boundary.** Managed auth provider (ADR-005) ile en olgun ve en güvenli entegrasyon yolu Next.js'tedir; token/session sunucu tarafında tutulabilir, tarayıcıya taşınması gereken sır azalır.
2. **Güvenli UX.** PRD §43.4 onay/ret gibi kararlarda *server-confirmed state* şart koşar; optimistic UI YASAK. Next.js'in server-side veri çekme modeli bunu doğal kılar.
3. **Dashboard performans hedefi** (p95 < 2.5 s) SSR ile daha kolay tutturulur.
4. Route haritası (PRD §43.1) dosya-tabanlı routing ile birebir eşlenir.

## Sonuçlar

**Pozitif**

- Server-side auth ve veri çekme; daha az client-side sır.
- İlk yükleme performansı.
- OpenAPI'den üretilen TypeScript client ile uçtan uca tip güvenliği.

**Negatif / risk**

- Next.js'in server/client bileşen sınırı yanlış kullanılırsa **business logic frontend'e sızabilir** → aşağıdaki uyum kuralları bunu engeller.
- Görsel canvas sonraki fazda geldiğinde ağır client-side bileşen entegrasyonu ek iş gerektirir (kabul edilen risk; canvas MVP dışı).

## Uyum kuralları (agent için bağlayıcı)

1. **Business logic frontend'de bulunamaz.** Yetki kararı, koşul değerlendirmesi, onay sırası, SLA hesabı **yalnız** backend'dedir. Frontend bunları yalnız **gösterir**.
2. Yetkisiz butonu gizlemek yeterli değildir; backend enforcement zorunludur.
3. Onay/ret gibi kararlarda **optimistic UI YASAK**; server-confirmed state gösterilir. Arka plan işi bitmeden "tamamlandı" bildirimi gösterilmez.
4. API tipleri OpenAPI sözleşmesinden **üretilir**; elle yazılmaz.
5. Her ekran şu state'leri implemente eder: loading, empty, permission-denied, not-found, validation-error, recoverable-server-error, processing/queued, success. Yalnız happy path ile story tamamlanamaz.
6. Domain katmanı Next.js'e bağımlı olamaz (frontend, backend domain'ini import etmez; sözleşme üzerinden konuşur).
7. Tarih/para gösterimi locale-aware olur; UTC → organizasyon timezone dönüşümü yalnız gösterim katmanındadır.

## Yeniden değerlendirme tetikleyicileri

- Workflow builder canvas MVP'ye alınırsa (canvas kütüphanesi kriteri yeniden ağırlık kazanır).
- Next.js'in server/client sınırı, güvenlik kurallarının uygulanmasını sürekli zorlaştırırsa.
