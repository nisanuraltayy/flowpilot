# ADR-001 — Backend Stack: Python + FastAPI + Pydantic + SQLAlchemy + Alembic

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-001 (**kapandı**)
- **İlgili PRD bölümleri:** §11, §26, §32.2, §46

## Bağlam

PRD backend için üç aday bırakmıştı: Python + FastAPI, TypeScript + NestJS, Java/Kotlin + Spring Boot. Karar kriterleri (PRD §26): ekip yetkinliği, workflow worker ekosistemi, tip güvenliği, background job, observability, test kolaylığı, AI entegrasyonu ve uzun vadeli bakım.

Ürünün çalışma modeli **solo developer + AI coding agent**'tir. Bu, "en güçlü ekosistem" kadar "tek kişinin sürdürebileceği bilişsel yük"ün de karar kriteri olduğu anlamına gelir.

## Değerlendirilen seçenekler

| Kriter | Python + FastAPI | TypeScript + NestJS | Kotlin + Spring Boot |
|---|---|---|---|
| Solo developer verimliliği | Yüksek | Orta | Düşük (boilerplate) |
| Tip güvenliği | Orta-yüksek (type hints + Pydantic runtime validation) | Yüksek (compile-time) | Yüksek |
| Runtime şema doğrulama | **Çok güçlü** (Pydantic) | Orta (class-validator) | Orta |
| Background worker | Olgun (RQ/Celery/custom polling) | Olgun (BullMQ) | Olgun |
| PostgreSQL + migration | **Çok güçlü** (SQLAlchemy + Alembic) | İyi (Prisma/TypeORM) | Çok güçlü (Flyway/Liquibase) |
| Observability (OpenTelemetry) | İyi | İyi | Çok iyi |
| AI/LLM ekosistemi (sonraki faz) | **En güçlü** | Orta | Zayıf |
| Operasyon maliyeti (tek kişi) | Düşük | Düşük | Yüksek (JVM tuning) |
| Frontend ile dil paylaşımı | Yok | **Var** | Yok |

**NestJS'in tek gerçek avantajı** frontend ile dil paylaşımıydı. Bu avantaj, sözleşme-öncelikli (OpenAPI'den tip üretimi) yaklaşımla büyük ölçüde telafi edilebilir; ayrıca aynı dili paylaşmak modül sınırlarının erimesi riskini artırır.

**Spring Boot** kurumsal ölçekte güçlüdür ancak solo developer için deployment ve boilerplate maliyeti orantısızdır.

## Karar

Backend: **Python 3.x + FastAPI + Pydantic + SQLAlchemy + Alembic**, PostgreSQL üzerinde.

- **FastAPI** — HTTP presentation katmanı (yalnız presentation).
- **Pydantic** — request/response DTO'ları, form schema doğrulama, workflow definition JSON schema doğrulama, event payload doğrulama.
- **SQLAlchemy** — infrastructure/persistence katmanı ORM'i (yalnız infrastructure).
- **Alembic** — versiyonlu migration.

## Gerekçe

1. Pydantic, FlowPilot'ın en yoğun ihtiyacı olan **runtime şema doğrulaması** (form schema, workflow definition JSON, event payload) için doğrudan bir çözümdür. Bu doğrulamalar sunucu tarafında zorunludur; compile-time tip güvenliği tek başına yetmez.
2. SQLAlchemy + Alembic; RLS politikaları, expand-migrate-contract akışı ve `FOR UPDATE SKIP LOCKED` gibi PostgreSQL'e özgü outbox ihtiyaçlarını doğrudan destekler.
3. Solo developer + agent modelinde en düşük bilişsel yük ve en hızlı iterasyon.
4. Sonraki fazdaki AI özellikleri için en olgun ekosistem (bu MVP'de kullanılmayacak, ancak stack değişimi maliyetinden kaçınılır).

## Sonuçlar

**Pozitif**

- Hızlı iterasyon; az boilerplate.
- Güçlü runtime doğrulama, sözleşme-öncelikli API (FastAPI OpenAPI üretir).
- PostgreSQL'e özgü yeteneklere tam erişim.

**Negatif / risk**

- Compile-time tip güvenliği TypeScript/Kotlin kadar güçlü değil → **statik type check kalite kapısı zorunludur**.
- Frontend ile dil paylaşılmıyor → **OpenAPI'den TypeScript client üretimi zorunludur**; el ile tip senkronizasyonu YASAK.
- Pydantic'in kolaylığı, domain modelinin farkında olmadan Pydantic'e bağlanma riski yaratır → aşağıdaki uyum kuralı bunu engeller.

## Uyum kuralları (agent için bağlayıcı)

1. **Domain katmanı FastAPI, SQLAlchemy veya Pydantic'e bağımlı olamaz.** Domain entity'leri düz Python sınıfları/dataclass'larıdır. Pydantic yalnız presentation/application sınırında (DTO, schema validation) kullanılır.
2. SQLAlchemy modelleri **yalnız** `infrastructure/persistence` altında bulunur ve domain'e sızmaz.
3. Generic repository YASAK; aggregate-specific repository kullanılır.
4. Statik type check ve lint zorunlu kalite kapısıdır.
5. Frontend tipleri OpenAPI sözleşmesinden **üretilir**; elle yazılmaz.

## Yeniden değerlendirme tetikleyicileri

- Workflow runtime spike'ı Python'da kabul edilemez performans/eşzamanlılık sınırlarına çarparsa.
- Ekip solo developer olmaktan çıkıp çoklu ekibe dönüşürse.
