# ADR-003 — Modüler Monolit + Arka Plan Worker'ları

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** —
- **İlgili PRD bölümleri:** §11.1, §11.3, §35, §38.1, §38.14, §39

## Bağlam

FlowPilot çok modüllü bir SaaS'tır (identity, organization, authorization, workflow design, workflow runtime, work management, approval, notification, document, audit, analytics). Mikroservis çekiciliği yüksektir; ancak ürün sınırları henüz değişkendir ve ekip solo developer + AI agent'tır.

Kritik teknik gözlem: FlowPilot'ın en önemli invariant'ları (approval kararı + state transition + outbox + audit) **tek transaction bütünlüğü** gerektirir. Mikroservis mimarisi bu bütünlüğü dağıtık transaction/saga karmaşıklığına dönüştürür.

## Değerlendirilen seçenekler

1. **Modüler monolit** — tek deployable, katı modül sınırları, ayrı worker process'leri.
2. Mikroservisler — servis başına deployable ve veritabanı.
3. Yapısız monolit — modül sınırı olmayan tek uygulama.

## Karar

**Modüler monolit.** Tek uygulama kod tabanı; ancak modül ve veri sahipliği sınırları **katı** korunur. Asenkron işler ayrı **worker process**'lerinde çalışır (web process içinde cron/timer YASAK).

Deployable birimler:

- `api` — senkron HTTP API (composition root)
- `worker` — outbox dispatcher, timer worker, notification consumer
- `web` — Next.js kullanıcı uygulaması

Aynı kod tabanı, aynı PostgreSQL; farklı process'ler.

## Gerekçe

1. Transaction bütünlüğü: state + outbox + audit aynı transaction'da yazılabilir.
2. Solo developer için dağıtık sistem operasyon maliyeti (tracing, deploy, versiyonlama, veri tutarlılığı) orantısızdır.
3. Ürün sınırları değişebilir; erken çizilen servis sınırları yanlış olur ve düzeltmesi pahalıdır.
4. MVP'de ölçek değil, ürün doğrulaması önemlidir.

## Sonuçlar

**Pozitif**

- Güçlü transaction sınırları; basit deploy ve debug.
- Modül sınırı korunduğu sürece ileride servis çıkarma (strangler pattern) mümkün.

**Negatif / risk**

- **En büyük risk:** Modül sınırlarının zamanla erimesi ("büyük çamur topu"). Aynı kod tabanında olmak, doğrudan import ve cross-module DB yazımını teknik olarak *kolay* kılar.
- Bu risk yalnız disiplinle değil, **CI fitness function'ları** ile engellenir (aşağıdaki uyum kuralları).

## Uyum kuralları (agent için bağlayıcı)

1. Bir modül başka modülün **tablosuna doğrudan yazamaz**.
2. Bir modül başka modülün **persistence modelini import edemez**.
3. Cross-module okuma: açık application contract / read model. Cross-module yazma: command veya integration event.
4. Domain katmanı infrastructure'a bağımlı olamaz.
5. `shared`/`common` paketi yalnız primitive, error base, ID, `Clock` ve telemetry sözleşmelerini barındırır; domain çöplüğü olamaz.
6. Asenkron iş **ayrı worker process**'te çalışır. Web process içinde cron veya in-memory timer YASAK.
7. Bu kurallar CI'da otomatik doğrulanır (bkz. [dependency-rules.md](../architecture/dependency-rules.md)). Fitness check kırmızıysa merge edilemez.
8. Mikroservise geçiş gerekirse **big-bang rewrite YASAK**; strangler pattern ile capability bazlı ayrılır.

## Yeniden değerlendirme tetikleyicileri

- Bir modülün ölçek profili (ör. notification veya analytics) diğerlerinden ölçülebilir şekilde ayrışırsa.
- Ekip büyür ve deploy çakışmaları ölçülebilir maliyet üretirse.
- Fitness function'ları sürekli ihlal ediliyorsa (sınırların erimesi sinyali) — çözüm önce disiplin, sonra ayrıştırma.
