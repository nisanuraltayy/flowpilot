# ADR-008 — Monorepo

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-008 (**kapandı**)
- **İlgili PRD bölümleri:** §32.2, §46

## Bağlam

FlowPilot üç deployable birim üretecektir: `api` (FastAPI), `worker` (outbox/timer consumer) ve `web` (Next.js). Ayrıca paylaşılan sözleşmeler (OpenAPI, AsyncAPI, workflow definition JSON Schema) ve bunlardan üretilen tipler bulunur.

Soru: bunlar tek repository'de mi, ayrı repository'lerde mi yaşamalı?

## Değerlendirilen seçenekler

| Kriter | Monorepo | Polyrepo |
|---|---|---|
| Sözleşme senkronizasyonu (API ↔ client tipleri) | **Atomik** — aynı PR'da değişir | Cross-repo koordinasyon; sürüm kayması riski |
| Dikey dilim (vertical slice) PR'ı | **Doğal** — backend + frontend tek PR | İki PR, iki review, iki merge sırası |
| Mimari fitness check (modül bağımlılıkları) | **Tek yerde** çalışır | Parçalı; cross-repo kural zorlanamaz |
| Atomik refactor | Mümkün | Zor |
| CI süresi | Uzayabilir (path-based filtreleme gerekir) | Daha kısa |
| Solo developer bilişsel yük | **Düşük** (tek klon, tek branch) | Yüksek (repo/branch senkronizasyonu) |
| Erişim kontrolü ayrıştırması | Kaba | İnce |

## Karar

**Monorepo.** Tek git repository; içinde `api`, `worker`, `web` uygulamaları, modüller, paylaşılan sözleşme paketi ve dokümantasyon.

Fiziksel yerleşim **[ADR-009](ADR-009-python-physical-layout.md)** ile kesinleştirilmiştir. Güncel yapı:

```text
/apps
  /backend     → TEK Python distribution (flowpilot-backend)
                 src/flowpilot/{shared,observability,config,modules,api,worker}
                 tests/{unit,integration,contract,security}
                 alembic.ini + migrations/   (TEK migration history)
  /web         → Next.js
/packages
  /contracts   → OpenAPI/AsyncAPI/JSON Schema + üretilen TS tipleri
  /ui          → frontend design system
/infra
  /containers  → Dockerfile'lar, docker-compose
/scripts       → fitness check, contract lint, secret scan
/tests/e2e     → tarayıcı e2e (web + API)
/docs
/.claude/rules
```

> **ADR-009 ile netleşen noktalar:** `api` ve `worker` ayrı Python projeleri **değildir** — aynı distribution'ın iki composition root'udur. `shared`, `observability`, `config` ve test altyapısı ayrı distribution **değildir**. Bounded context'ler `flowpilot.modules.<snake_case>` altındadır; **tireli klasör adı Python import yolunda kullanılamaz**.

## Gerekçe

1. **Sözleşme bütünlüğü.** ADR-001 ve ADR-002 birlikte, backend (Python) ile frontend (TypeScript) arasında OpenAPI'den üretilen tiplere dayanır. Monorepo, sözleşme değişikliği ile tüketicisinin **aynı commit'te** güncellenmesini garanti eder. Polyrepo'da bu, sürüm kayması ve "çalışıyordu ama artık değil" sınıfı hatalar üretir.
2. **Dikey dilim çalışma modeli.** İlk dilim (satın alma talebi) tek bir PR'da uçtan uca doğrulanabilir olmalıdır.
3. **Fitness function'ları.** Modüler monolitin (ADR-003) en büyük riski sınırların erimesidir. Bu riski engelleyen otomatik kontroller ancak tüm kodun tek yerde olduğu bir repo'da anlamlıdır.
4. Solo developer için tek klon, tek branch, tek CI.

## Sonuçlar

**Pozitif**

- Atomik sözleşme + implementasyon değişikliği.
- Tek yerde çalışan mimari kurallar.
- Basit yerel geliştirme.

**Negatif / risk**

- **Repo büyüdükçe CI yavaşlar** → path-based CI filtreleme (değişen alana göre job çalıştırma) baştan kurulmalıdır.
- Monorepo, modül sınırlarının erimesini **teknik olarak kolaylaştırır** (her şey import edilebilir mesafede) → ADR-003'ün fitness function'ları bu yüzden opsiyonel değil, **zorunludur**.
- Kaba erişim kontrolü: repo'ya erişen her şeye erişir. Solo developer modelinde şu an sorun değil; ekip büyürse yeniden değerlendirilir.

## Uyum kuralları (agent için bağlayıcı)

1. Monorepo, "her şey her şeyi import edebilir" demek **değildir**. Modül bağımlılık kuralları (bkz. [dependency-rules.md](../architecture/dependency-rules.md)) CI'da zorlanır.
2. Sözleşme değişikliği ve tüketicisinin güncellenmesi **aynı PR'da** olur.
3. Frontend tipleri `packages/contracts` içinde OpenAPI'den **üretilir**; elle yazılmaz.
4. Bir PR yine de **tek ana amaç** taşır. Monorepo, PR'ı büyütmek için gerekçe değildir.
5. Career Copilot bu monorepo'nun parçası **değildir** ve buraya eklenmez.

## Yeniden değerlendirme tetikleyicileri

- CI süresi, path filtrelemeye rağmen geliştirme akışını bozarsa.
- Ekip büyür ve ince taneli erişim kontrolü (kod sahipliği/gizlilik) gereksinimi doğarsa.
- Bir modül gerçekten ayrı bir servise çıkarılırsa (strangler pattern), o servis kendi repo'suna taşınabilir.
