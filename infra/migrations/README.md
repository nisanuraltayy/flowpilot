# infra/migrations — (kullanılmıyor)

> ⛔ **Migration'lar BURADA DEĞİL.**
>
> Tek migration history: **`apps/backend/migrations/`** + `apps/backend/alembic.ini`
> Karar: [ADR-009](../../docs/adr/ADR-009-python-physical-layout.md)

## Neden burada değil

Alembic, backend Python distribution'ının bir parçasıdır: `env.py` uygulama modellerini ve `DATABASE_URL` konfigürasyonunu import eder. Migration'ları backend'in dışına koymak, ya bir import hack'i ya da ikinci bir konfigürasyon kopyası gerektirir.

**Bu dizin ikinci bir source of truth OLAMAZ.** İki migration history, aynı veritabanı üzerinde sıralanamayan bağımsız zincirler üretir — foreign key'ler ve RLS politikaları modüller arası bir sıra zorunluluğu doğurduğu için bu, sessizce bozulan bir düzendir.

## Migration kuralları

Kurallar (expand → deploy → backfill → switch → verify → contract, RLS zorunluluğu, forward-only) [.claude/rules/database.md](../../.claude/rules/database.md) §8'de tanımlıdır ve `apps/backend/migrations/` için geçerlidir.

## Durum

Boş ve boş kalacak. `infra/` yalnız [container tanımlarını](../containers/README.md) barındırır.

Gerçek migration history artık **`apps/backend/migrations/versions/`** altındadır
(revision'lar: `0001` — identity + organization tabloları ve RLS policy'leri; `0002` — auth identity mapping: auth_provider + provider_subject + uq constraint; `0003` — workflow runtime core: `workflow_runtime_*` tabloları, RLS ENABLE+FORCE + tenant policy'leri, published version + append-only event immutability trigger'ları).
Komutlar: [apps/backend/README.md](../../apps/backend/README.md).
